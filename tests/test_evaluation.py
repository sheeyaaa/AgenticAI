import json
from pathlib import Path

from prd_agents.evaluation import (
    EvaluationConfig,
    EvaluationResult,
    _completed_keys,
    run_evaluation,
    summarize,
)


def test_summary_reports_statistics_and_cost_projection() -> None:
    results = [
        EvaluationResult(
            run_id="a", scenario_id="one", repeat=1,
            started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:01Z",
            status="success", total_latency_seconds=1.0,
            estimated_cost_usd=0.25,
        ),
        EvaluationResult(
            run_id="b", scenario_id="one", repeat=2,
            started_at="2026-01-01T00:00:00Z", finished_at="2026-01-01T00:00:03Z",
            status="failure", total_latency_seconds=3.0,
            estimated_cost_usd=0.50,
        ),
    ]
    summary = summarize(results)
    assert summary["success_rate"] == 0.5
    assert summary["latency_seconds"]["median"] == 2.0
    assert summary["cost"]["projected_100_prds_usd"] == 37.5


def test_completed_keys_support_resume(tmp_path: Path) -> None:
    path = tmp_path / "raw_results.jsonl"
    path.write_text(json.dumps({"scenario_id": "one", "repeat": 2}) + "\n")
    assert _completed_keys(path) == {("one", 2)}


def test_evaluation_resumes_and_writes_reports(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "tiny.md").write_text(
        "# Tiny\n\n- The user can view the welcome page.\n",
        encoding="utf-8",
    )
    output = tmp_path / "results"
    config = EvaluationConfig(scenarios_dir=scenarios, output_dir=output, repeats=2)
    raw_path = run_evaluation(config)
    assert len(raw_path.read_text(encoding="utf-8").splitlines()) == 2
    run_evaluation(config)
    assert len(raw_path.read_text(encoding="utf-8").splitlines()) == 2
    assert (output / "reports" / "report.md").exists()
    assert (output / "reports" / "runtime_distribution.png").exists()
