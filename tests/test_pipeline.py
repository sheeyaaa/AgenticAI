from pathlib import Path
from prd_agents.config import AppConfig
from prd_agents.cli import sample_paths
from prd_agents.pipeline import run_pipeline


def test_bundled_samples_are_available() -> None:
    names = {path.name for path in sample_paths()}
    assert {"sample_prd.md", "travel_booking_prd.md", "banking_transfer_prd.md", "ecommerce_catalog_prd.md"} <= names


def test_pipeline_exports_typed_outputs(tmp_path: Path) -> None:
    state = run_pipeline(
        Path("samples/sample_prd.md"),
        tmp_path,
        AppConfig(max_iterations=2, quality_threshold=1.0, coverage_target=1.0),
    )
    assert state.document is not None
    assert state.requirement_points
    assert state.test_cases
    assert state.validation_report is not None
    assert (tmp_path / "test_cases.json").exists()
    assert (tmp_path / "run_report.json").exists()
    assert len(state.write_log) >= 10


def test_fake_model_can_supply_json(tmp_path: Path) -> None:
    class Fake:
        def complete(self, prompt: str) -> str:
            if "Extract" in prompt:
                return '```json\n[{"id":"REQ-X","text":"The system displays a welcome page","source_chunk_id":"chunk-1","acceptance_criteria":[]}]\n```'
            return '[{"id":"TC-X","req_ids":["REQ-X"],"title":"Welcome page","preconditions":[],"steps":["Open app"],"expected_result":"Welcome page is visible","type":"positive","priority":"high"}]'

    state = run_pipeline(Path("samples/sample_prd.md"), tmp_path, AppConfig(max_iterations=1),
                         {"extractor": Fake(), "generator": Fake()})
    assert state.requirement_points[0].id == "REQ-X"
    assert state.test_cases[0].id == "TC-X"


def test_llm_run_report_aggregates_provider_usage(tmp_path: Path) -> None:
    class Fake:
        def __init__(self, response: str, role: str) -> None:
            self.response = response
            self.role = role
            self.calls = 0

        def complete(self, prompt: str) -> str:
            self.calls += 1
            return self.response

        @property
        def usage_summary(self) -> dict[str, object]:
            return {
                "provider": "groq",
                "model": self.role + "-model",
                "calls": self.calls,
                "input_tokens": 10 * self.calls,
                "output_tokens": 5 * self.calls,
                "usage_available": self.calls > 0,
                "estimated_cost_usd": 0.0001 * self.calls,
                "fallback_used": False,
            }

    clients = {
        "extractor": Fake(
            '[{"id":"REQ-X","text":"A user can sign in",'
            '"source_chunk_id":"chunk-1","acceptance_criteria":[]}]', "extractor",
        ),
        "generator": Fake(
            '[{"id":"TC-X","req_ids":["REQ-X"],"title":"Sign in",'
            '"expected_result":"The user is signed in","type":"positive"}]', "generator",
        ),
        "critic": Fake(
            '{"score":1,"coverage_score":1,"missing_req_ids":[],"feedback":[]}', "critic",
        ),
        "selenium": Fake(
            '[{"test_case_id":"TC-X","code":"def test_sign_in():\\n    assert True\\n",'
            '"locators":[]}]', "selenium",
        ),
    }
    config = AppConfig(
        execution_mode="llm", max_iterations=1,
        quality_threshold=1, coverage_target=1,
    )
    state = run_pipeline(Path("samples/sample_prd.md"), tmp_path, config, clients)

    assert state.run_report is not None
    assert state.run_report.estimated_token_counts == {
        "input_tokens": 40, "output_tokens": 20,
    }
    assert state.run_report.estimated_api_cost_usd == 0.0004
    assert set(state.run_report.provider_usage) == set(clients)
