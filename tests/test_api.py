from pathlib import Path
import io
import sqlite3
import urllib.error

from fastapi.testclient import TestClient

from api.main import create_app
from prd_agents.models import (
    BlackboardState,
    CoverageReport,
    RequirementPoint,
    RunReport,
    SeleniumScript,
    TestCase as CaseModel,
    ValidationReport,
)
from prd_agents.monitoring import MonitoringEvent


def _fake_pipeline(prd_path: Path, out_dir: Path, config, clients,
                   run_id: str | None = None) -> BlackboardState:
    assert config.arch == "blackboard"
    assert config.pipeline_pattern == "sequential"
    assert config.pipeline == "sequential_loop"
    requirement = RequirementPoint(
        id="REQ-001", text="A user can sign in", source_chunk_id="chunk-1",
    )
    case = CaseModel(
        id="TC-001", req_ids=[requirement.id], title="Sign in",
        expected_result="The user is signed in", type="positive",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    monitoring_dir = out_dir / config.monitoring_dir
    monitoring_dir.mkdir(parents=True, exist_ok=True)
    event = MonitoringEvent(
        run_id=run_id or "pipeline-event",
        trace_id="trace",
        agent_name="extractor",
        orchestration_pattern="sequential",
        event_type="agent_completed",
        status="completed",
        duration_ms=2,
    )
    (monitoring_dir / "events.jsonl").write_text(event.model_dump_json() + "\n")
    return BlackboardState(
        requirement_points=[requirement],
        test_cases=[case],
        coverage=CoverageReport(
            covered_requirement_ids=[requirement.id],
            score=1,
        ),
        selenium_scripts=[
            SeleniumScript(
                test_case_id=case.id,
                filename="test_tc-001.py",
                code="def test_tc_001():\n    assert True\n",
            )
        ],
        validation_report=ValidationReport(valid=True, validated_count=1),
        run_report=RunReport(
            run_id=run_id,
            source_path=str(prd_path), iterations=1, final_quality_score=1,
            final_coverage_score=1, deterministic_coverage_percent=100,
            remaining_gaps={}, requirement_count=1, test_case_count=1,
            elapsed_seconds=0.1, estimated_token_counts={},
            scripts_validated=1,
        ),
    )


def _model_config_payload() -> dict:
    return {
        "roles": {
            "extractor": {
                "provider": "ollama", "model": "llama3.1:8b",
            },
            "generator": {
                "provider": "ollama", "model": "qwen2.5:7b-instruct",
            },
            "critic": {
                "provider": "ollama", "model": "mistral:7b-instruct",
            },
            "selenium": {
                "provider": "ollama", "model": "qwen2.5:7b-instruct",
            },
        }
    }


def test_health_samples_and_cors(tmp_path: Path) -> None:
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline,
                     cors_origins=["https://frontend.example"])
    with TestClient(app) as client:
        health = client.get("/health")
        samples = client.get("/api/samples")
        preflight = client.options(
            "/api/run",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        put_preflight = client.options(
            "/api/models/config",
            headers={
                "Origin": "https://frontend.example",
                "Access-Control-Request-Method": "PUT",
            },
        )
    assert health.status_code == 200
    assert health.json()["architecture"] == "blackboard"
    assert health.json()["orchestration_pattern"] == "sequential"
    assert any(item["id"] == "sample_prd" for item in samples.json()["items"])
    assert preflight.headers["access-control-allow-origin"] == "https://frontend.example"
    assert "PUT" in put_preflight.headers["access-control-allow-methods"]


def test_default_cors_allows_common_local_frontend_ports(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        responses = [
            client.options(
                "/api/runs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            for origin in (
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
            )
        ]

    assert [response.headers["access-control-allow-origin"] for response in responses] == [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]


def test_upload_run_list_get_results_and_events(tmp_path: Path) -> None:
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        upload = client.post(
            "/api/upload-prd",
            files={"file": ("my-prd.md", b"# Login\nUsers can sign in.", "text/markdown")},
        )
        assert upload.status_code == 201
        upload_id = upload.json()["upload_id"]

        submitted = client.post("/api/run", json={"upload_id": upload_id})
        run_id = submitted.json()["run_id"]
        record = client.get(f"/api/runs/{run_id}")
        listing = client.get("/api/runs")
        results = client.get(f"/api/runs/{run_id}/results")
        events = client.get(f"/api/runs/{run_id}/events")

    assert submitted.status_code == 202
    assert record.status_code == 200
    assert record.json()["status"] == "completed"
    assert record.json()["execution_time_seconds"] >= 0
    assert listing.json()["total"] == 1
    assert results.status_code == 200
    assert results.json()["requirements"][0]["id"] == "REQ-001"
    assert results.json()["validation_report"]["valid"] is True
    assert events.status_code == 200
    assert events.json()["events"][0]["event_type"] == "agent_completed"
    assert events.json()["events"][0]["run_id"] == run_id
    assert results.json()["run_report"]["run_id"] == run_id


def test_sample_run_ids_are_unique_and_errors_are_structured(tmp_path: Path) -> None:
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        first = client.post("/api/run", json={"sample_id": "sample_prd"})
        second = client.post("/api/run", json={"sample_id": "sample_prd"})
        missing = client.get("/api/runs/not-a-run")
        invalid_source = client.post("/api/run", json={})
        both_sources = client.post(
            "/api/run", json={"sample_id": "sample_prd", "upload_id": "anything"}
        )
        missing_results = client.get("/api/runs/not-a-run/results")
        missing_events = client.get("/api/runs/not-a-run/events")

    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] != second.json()["run_id"]
    assert missing.status_code == 404
    assert missing_results.status_code == missing_events.status_code == 404
    assert invalid_source.status_code == both_sources.status_code == 422
    assert isinstance(invalid_source.json()["detail"], list)


def test_upload_validation_and_failed_pipeline_status(tmp_path: Path) -> None:
    def failing_pipeline(*args, **kwargs):
        raise RuntimeError("internal detail")

    app = create_app(tmp_path, pipeline_runner=failing_pipeline)
    with TestClient(app) as client:
        bad_extension = client.post(
            "/api/upload-prd",
            files={"file": ("unsafe.exe", b"no", "application/octet-stream")},
        )
        empty = client.post(
            "/api/upload-prd",
            files={"file": ("empty.md", b"", "text/markdown")},
        )
        uploaded = client.post(
            "/api/upload-prd",
            files={"file": ("valid.txt", b"Some PRD text", "text/plain")},
        )
        run = client.post("/api/run", json={"upload_id": uploaded.json()["upload_id"]})
        status = client.get(f"/api/runs/{run.json()['run_id']}")
        results = client.get(f"/api/runs/{run.json()['run_id']}/results")

    assert bad_extension.status_code == 400
    assert empty.status_code == 400
    assert run.status_code == 202
    assert status.json()["status"] == "failed"
    assert status.json()["error_type"] == "RuntimeError"
    assert "internal detail" not in status.text
    assert results.status_code == 409


def test_default_runner_calls_existing_pipeline_with_api_run_id(
    tmp_path: Path, monkeypatch,
) -> None:
    import api.run_manager as run_manager

    calls = {}

    def pipeline_spy(prd_path, out_dir, config, clients, *, run_id):
        calls.update({
            "prd_path": prd_path,
            "config": config,
            "clients": clients,
            "run_id": run_id,
        })
        return _fake_pipeline(prd_path, out_dir, config, clients, run_id=run_id)

    monkeypatch.setattr(run_manager, "run_pipeline", pipeline_spy)
    monkeypatch.setattr(run_manager, "create_model_clients", lambda config: {})
    app = create_app(tmp_path)
    with TestClient(app) as client:
        roles = _model_config_payload()["roles"]
        roles["extractor"] = {
            "provider": "gemini", "model": "gemini-2.5-flash",
            "credential_ref": "GEMINI_API_KEY",
        }
        configured = client.put("/api/models/config", json={"roles": roles})
        submitted = client.post("/api/run", json={"sample_id": "sample_prd"})
        run_id = submitted.json()["run_id"]
        events = client.get(f"/api/runs/{run_id}/events").json()["events"]

    assert configured.status_code == 200
    assert calls["run_id"] == run_id
    assert calls["config"].arch == "blackboard"
    assert calls["config"].pipeline_pattern == "sequential"
    assert calls["config"].pipeline == "sequential_loop"
    assert calls["config"].models["extractor"].provider == "gemini"
    assert calls["config"].models["extractor"].name == "gemini-2.5-flash"
    assert events[0]["run_id"] == run_id


def test_model_config_get_put_and_test_use_env_references(
    tmp_path: Path, monkeypatch,
) -> None:
    credentials = {
        "GEMINI_API_KEY": "test-gemini-primary",
        "GEMINI_API_KEY2": "test-gemini-secondary",
        "GROQ1": "test-groq-primary",
        "GROQ2": "test-groq-secondary",
    }
    for name, value in credentials.items():
        monkeypatch.setenv(name, value)
    roles = _model_config_payload()["roles"]
    roles.update({
        "extractor": {
            "provider": "gemini", "model": "gemini-2.5-flash",
            "credential_ref": "GEMINI_API_KEY",
        },
        "generator": {
            "provider": "gemini", "model": "gemini-2.0-flash",
            "credential_ref": "GEMINI_API_KEY2",
        },
        "critic": {
            "provider": "groq", "model": "llama-3.3-70b-versatile",
            "credential_ref": "GROQ1",
        },
        "selenium": {
            "provider": "groq", "model": "llama-3.1-8b-instant",
            "credential_ref": "GROQ2",
        },
    })
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return io.BytesIO(b'{"models":[{"name":"models/gemini-2.5-flash"}]}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        updated = client.put("/api/models/config", json={"roles": roles})
        retrieved = client.get("/api/models/config")
        tested = client.post("/api/models/test", json={"role": "extractor"})

    assert updated.status_code == retrieved.status_code == 200
    assert retrieved.json()["roles"]["extractor"]["provider"] == "gemini"
    assert retrieved.json()["roles"]["generator"]["model"] == "gemini-2.0-flash"
    assert retrieved.json()["roles"]["critic"]["credential_configured"] is True
    assert retrieved.json()["roles"]["critic"]["credential_ref_masked"] == "GROQ****1"
    assert tested.status_code == 200
    assert tested.json()["reachable"] is True
    assert captured["request"].get_header("X-goog-api-key") == credentials["GEMINI_API_KEY"]
    assert not any(value in updated.text + retrieved.text + tested.text
                   for value in credentials.values())

    with sqlite3.connect(tmp_path / "api.sqlite3") as connection:
        saved = connection.execute(
            "SELECT roles_json FROM model_configs WHERE config_id = 1"
        ).fetchone()[0]
    assert all(value not in saved for value in credentials.values())
    assert "GEMINI_API_KEY2" in saved
    assert "GROQ2" in saved


def test_model_config_update_preserves_omitted_credential_reference(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-secret")
    roles = _model_config_payload()["roles"]
    roles["extractor"] = {
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "credential_ref": "GEMINI_API_KEY",
    }
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        initial = client.put("/api/models/config", json={"roles": roles})
        roles["extractor"] = {
            "provider": "gemini",
            "model": "gemini-2.0-flash",
        }
        updated = client.put("/api/models/config", json={"roles": roles})
        retrieved = client.get("/api/models/config")

    assert initial.status_code == updated.status_code == retrieved.status_code == 200
    assert retrieved.json()["roles"]["extractor"]["model"] == "gemini-2.0-flash"
    assert retrieved.json()["roles"]["extractor"]["credential_configured"] is True
    assert retrieved.json()["roles"]["extractor"]["credential_ref_masked"] == "GEMI****_KEY"


def test_model_config_reports_missing_key_without_network_call(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def unexpected_request(*args, **kwargs):
        raise AssertionError("Missing credentials must not trigger a network request.")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_request)
    roles = _model_config_payload()["roles"]
    roles["extractor"] = {
        "provider": "gemini", "model": "gemini-2.5-flash",
        "credential_ref": "GEMINI_API_KEY",
    }
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        saved = client.put("/api/models/config", json={"roles": roles})
        status = client.get("/api/models/config")
        tested = client.post("/api/models/test", json={"role": "extractor"})

    assert saved.status_code == 200
    assert status.json()["roles"]["extractor"]["credential_configured"] is False
    assert tested.status_code == 200
    assert tested.json()["configured"] is False
    assert tested.json()["error_type"] == "configuration"


def test_model_config_rejects_incompatible_provider_model(
    tmp_path: Path,
) -> None:
    roles = _model_config_payload()["roles"]
    roles["critic"] = {
        "provider": "groq", "model": "gemini-2.5-flash",
        "credential_ref": "GROQ1",
    }
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        response = client.put("/api/models/config", json={"roles": roles})

    assert response.status_code == 422
    assert "Gemini model identifiers cannot be used with Groq" in response.text


def test_model_test_returns_safe_provider_failure(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("GROQ1", "test-provider-secret")

    def unavailable(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"provider secret detail"),
        )

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    roles = _model_config_payload()["roles"]
    roles["critic"] = {
        "provider": "groq", "model": "llama-3.3-70b-versatile",
        "credential_ref": "GROQ1",
    }
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        client.put("/api/models/config", json={"roles": roles})
        response = client.post("/api/models/test", json={"role": "critic"})

    assert response.status_code == 200
    assert response.json()["reachable"] is False
    assert response.json()["error_type"] == "authentication"
    assert "test-provider-secret" not in response.text
    assert "provider secret detail" not in response.text


def test_provider_validation_endpoint_never_returns_api_key(
    tmp_path: Path, monkeypatch,
) -> None:
    import io

    monkeypatch.setenv("GENERATOR_PROVIDER", "groq")
    monkeypatch.setenv("GENERATOR_MODEL", "test-model")
    monkeypatch.setenv("GENERATOR_API_KEY", "never-return-this-key")
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: io.BytesIO(b'{"data":[{"id":"test-model"}]}'),
    )
    app = create_app(tmp_path, pipeline_runner=_fake_pipeline)
    with TestClient(app) as client:
        response = client.post(
            "/api/providers/validate", json={"role": "generator"},
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "groq"
    assert response.json()["model_available"] is True
    assert "never-return-this-key" not in response.text
