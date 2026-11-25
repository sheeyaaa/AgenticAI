from pathlib import Path

import pytest

from prd_agents.config import AppConfig
from prd_agents.guardrails import GuardrailViolation, validate_document
from prd_agents.document import parse_document
from prd_agents.pipeline import run_pipeline


def test_guardrail_report_detects_injection_and_abuse() -> None:
    document = parse_document(Path("samples/guardrail_attack_prd.md"))
    report = validate_document(document)
    assert report.allowed is False
    assert {finding.category for finding in report.findings} == {
        "prompt_injection",
        "abusive_language",
    }


def test_pipeline_stops_before_writing_agent_outputs(tmp_path: Path) -> None:
    with pytest.raises(GuardrailViolation, match="PRD rejected by guardrails"):
        run_pipeline(
            Path("samples/guardrail_attack_prd.md"),
            tmp_path,
            AppConfig(),
        )
    events = (tmp_path / "monitoring" / "events.jsonl").read_text().splitlines()
    assert any('"event_type":"validation_failed"' in event
               for event in events)
    assert not (tmp_path / "test_cases.json").exists()


def test_safe_prd_passes_guardrails() -> None:
    document = parse_document(Path("samples/sample_prd.md"))
    assert validate_document(document).allowed is True
