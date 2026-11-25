import json
import time
from pathlib import Path

import pytest

from prd_agents.config import AppConfig
from prd_agents.pipeline import run_pipeline


def _config(pattern: str, **kwargs) -> AppConfig:
    values = {
        "pipeline_pattern": pattern,
        "max_iterations": 1,
        "quality_threshold": 1.0,
        "coverage_target": 1.0,
    }
    values.update(kwargs)
    return AppConfig(
        **values,
    )


@pytest.mark.parametrize("pattern", ["sequential", "parallel", "hierarchical"])
def test_each_pattern_writes_blackboard_and_report(tmp_path: Path, pattern: str) -> None:
    state = run_pipeline(
        Path("samples/sample_prd.md"), tmp_path / pattern, _config(pattern)
    )
    assert state.document is not None
    assert state.coverage is not None
    assert state.run_report is not None
    assert state.run_report.orchestration_pattern == pattern
    assert (tmp_path / pattern / "monitoring" / "events.jsonl").exists()


def test_parallel_pattern_records_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import prd_agents.orchestration as orchestration
    import prd_agents.pipeline as pipeline

    original_coverage = orchestration.check_coverage
    original_critique = pipeline._critique

    def slow_coverage(*args, **kwargs):
        time.sleep(0.15)
        return original_coverage(*args, **kwargs)

    def slow_critique(*args, **kwargs):
        time.sleep(0.15)
        return original_critique(*args, **kwargs)

    monkeypatch.setattr(orchestration, "check_coverage", slow_coverage)
    monkeypatch.setattr(pipeline, "_critique", slow_critique)
    output = tmp_path / "parallel"
    run_pipeline(Path("samples/sample_prd.md"), output, _config("parallel"))
    summary = json.loads((output / "monitoring" / "summary.json").read_text())
    assert summary["maximum_observed_concurrency"] >= 2


def test_hierarchical_revision_is_bounded(tmp_path: Path) -> None:
    config = _config("hierarchical", max_hierarchy_cycles=1,
                     quality_threshold=2.0, coverage_target=2.0)
    state = run_pipeline(Path("samples/sample_prd.md"), tmp_path, config)
    events = (tmp_path / "monitoring" / "events.jsonl").read_text().splitlines()
    revisions = [line for line in events if "revision_requested" in line]
    assert len(revisions) <= 1
    assert state.run_report is not None
