import ast
from pathlib import Path

import pytest

from prd_agents.models import BrowserAction, Locator, SeleniumScript, TestCase as Case
from prd_agents.models import CoverageReport, RequirementPoint
from prd_agents.pipeline import (
    _critique,
    _generate_cases,
    _generate_selenium_scripts,
    _script_for,
    export_suite,
    validate_scripts,
)
from prd_agents.blackboard import Blackboard
from prd_agents.config import AppConfig
from prd_agents.model_client import create_model_clients


def _case(case_id: str = "TC-001", test_type: str = "positive") -> Case:
    return Case(
        id=case_id,
        req_ids=["REQ-001"],
        title="Login",
        steps=["Open login", "Submit credentials"],
        expected_result="Dashboard is displayed",
        type=test_type,
        actions=[
            BrowserAction(action="navigate", value="/login"),
            BrowserAction(
                action="fill", value="alice",
                locator=Locator(strategy="id", value="username"),
            ),
            BrowserAction(
                action="assert_visible",
                locator=Locator(strategy="id", value="dashboard"),
            ),
        ],
    )


def test_structured_cases_generate_distinct_scripts_and_use_configured_url() -> None:
    login = _script_for(_case(), "https://test.example")
    negative = _script_for(_case("TC-002", "negative"), "https://test.example")
    assert login != negative
    assert "https://test.example" in login
    assert "username" in login
    assert "dashboard" in login
    ast.parse(login)
    assert "driver.quit()" in login


def test_missing_ui_information_is_explicitly_failed() -> None:
    script = _script_for(_case("TC-003").model_copy(update={"actions": []}))
    assert "Insufficient UI information" in script
    assert validate_scripts([SeleniumScript(
        test_case_id="TC-003", filename="test_tc-003.py", code=script,
    )]).valid


def test_generated_fallback_ids_are_unique() -> None:
    requirements = [
        {"id": "REQ-001", "text": "The user can log in", "source_chunk_id": "chunk-1"},
    ]

    class Fake:
        def complete(self, prompt: str) -> str:
            return (
                '[{"id":"TC-001","req_ids":["REQ-001"],"title":"a",'
                '"expected_result":"ok","type":"positive"},'
                '{"id":"TC-001","req_ids":["REQ-001"],"title":"b",'
                '"expected_result":"rejected","type":"negative"}]'
            )

    from prd_agents.models import RequirementPoint
    cases = _generate_cases(
        [RequirementPoint.model_validate(requirements[0])], [], Fake(),
    )
    assert [case.id for case in cases] == ["TC-001", "TC-002"]


def test_validation_aggregates_syntax_and_structure_failures() -> None:
    report = validate_scripts([
        SeleniumScript(test_case_id="TC-001", filename="good.py",
                       code="def test_good():\n    assert True\n"),
        SeleniumScript(test_case_id="TC-002", filename="bad.py",
                       code="def broken(:\n"),
    ])
    assert report.valid is False
    assert report.validated_count == 1
    assert report.rejected_count == 1
    assert any("bad.py" in error for error in report.errors)


def test_export_rejects_duplicate_filenames(tmp_path: Path) -> None:
    board = Blackboard()
    board.write("generator", "test_cases", [_case(), _case("TC-002")])
    board.write("validator", "selenium_scripts", [
        SeleniumScript(test_case_id="TC-001", filename="duplicate.py", code=""),
        SeleniumScript(test_case_id="TC-002", filename="duplicate.py", code=""),
    ])
    with pytest.raises(ValueError, match="unique"):
        export_suite(tmp_path, board.snapshot())


def test_model_timeout_is_shared_by_all_configured_clients() -> None:
    config = AppConfig(execution_mode="llm", model_timeout_seconds=600)
    clients = create_model_clients(config)
    assert {client.timeout for client in clients.values()} == {600}


def test_configured_selenium_model_returns_typed_unique_scripts() -> None:
    class Fake:
        def complete(self, prompt: str) -> str:
            return (
                '[{"test_case_id":"TC-001","code":"def test_login():\\n    assert True\\n",'
                '"locators":[]}]'
            )

    scripts = _generate_selenium_scripts(
        [_case()], Fake(), "https://app.example", use_llm=True,
    )
    assert len(scripts) == 1
    assert scripts[0].filename == "test_tc-001.py"
    assert scripts[0].test_case_id == "TC-001"
    assert "def test_login" in scripts[0].code


def test_critic_string_feedback_is_normalized_to_contract() -> None:
    class Fake:
        def complete(self, prompt: str) -> str:
            return '{"score":0.9,"coverage_score":1,"missing_req_ids":[],"feedback":"Looks good."}'

    requirements = [RequirementPoint(
        id="REQ-001", text="The user can log in", source_chunk_id="chunk-1",
    )]
    critique = _critique(
        requirements, [_case()], CoverageReport(score=1), Fake(),
    )
    assert critique.feedback == ["Looks good."]
