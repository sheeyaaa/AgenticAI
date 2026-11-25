"""Pipeline orchestration, deterministic fallbacks, script generation, and validation."""
from __future__ import annotations

import ast
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Protocol

from .blackboard import Blackboard
from .config import AppConfig
from .coverage import check_coverage
from .document import chunk_document, parse_document
from .models import (
    BlackboardState,
    BrowserAction,
    Critique,
    IterationRecord,
    RequirementPoint,
    SeleniumScript,
    TestCase,
    Chunks,
    Document,
    RequirementPoints,
    TestCases,
    ValidationReport,
    RunReport,
)
from .monitoring import Monitor, build_adk_callbacks
from .prompts import prompt_prefix


class ModelClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class ModelOutputError(ValueError):
    """Raised when an LLM response does not satisfy its required JSON contract."""


def _parse_model_json(response: str) -> Any:
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", response.strip(), re.DOTALL | re.IGNORECASE
    )
    return json.loads(fenced.group(1) if fenced else response)


def _agent_status(agent: str, status: str, detail: str = "") -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[agent:{agent}] {status}{suffix}", flush=True)


def _unique_id(prefix: str, used: set[str]) -> str:
    number = 1
    while f"{prefix}-{number:03d}" in used:
        number += 1
    value = f"{prefix}-{number:03d}"
    used.add(value)
    return value


def _normalise_requirements(items: list[dict], chunks: list) -> list[RequirementPoint]:
    result: list[RequirementPoint] = []
    used: set[str] = set()
    chunk_ids = {chunk.id for chunk in chunks}
    for item in items:
        try:
            point = RequirementPoint.model_validate(item)
        except (TypeError, ValueError):
            continue
        if point.source_chunk_id not in chunk_ids or not point.text.strip():
            continue
        point.id = point.id if point.id and point.id not in used else _unique_id("REQ", used)
        used.add(point.id)
        if any(point.text.casefold() == existing.text.casefold() for existing in result):
            continue
        result.append(point)
    return result


def _extract_requirements(chunks: list, client: ModelClient | None,
                          allow_fallback: bool = False) -> list[RequirementPoint]:
    if client:
        try:
            raw = _parse_model_json(client.complete(
                prompt_prefix("extractor", max(0, len(chunks) - 1))
                + " " + json.dumps([chunk.model_dump() for chunk in chunks])
            ))
            if isinstance(raw, list):
                result = _normalise_requirements(raw, chunks)
                if result:
                    return result
            raise ModelOutputError("Extractor response contained no valid requirements.")
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            if not allow_fallback:
                raise ModelOutputError("Extractor response did not match the requirement JSON contract.") from None

    points: list[RequirementPoint] = []
    used_text: set[str] = set()
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", chunk.text):
            text = sentence.strip(" -:;")
            words = text.split()
            if len(words) < 4 or text.startswith("#") or text.casefold() in used_text:
                continue
            if re.match(r"^(overview|introduction|notes?|background|purpose)\b", text, re.I):
                continue
            used_text.add(text.casefold())
            points.append(RequirementPoint(
                id=_unique_id("REQ", {point.id for point in points}),
                text=text,
                source_chunk_id=chunk.id,
                source_section=chunk.section_heading,
            ))
    return points


def _normalise_cases(items: list[dict], existing: list[TestCase]) -> list[TestCase]:
    cases = list(existing)
    used = {case.id for case in cases}
    for item in items:
        try:
            case = TestCase.model_validate(item)
        except (TypeError, ValueError):
            continue
        if not case.req_ids or case.id in used:
            case.id = _unique_id("TC", used)
        else:
            used.add(case.id)
        cases.append(case)
    return cases


def _generate_cases(requirements: list[RequirementPoint], existing: list[TestCase],
                    client: ModelClient | None, allow_fallback: bool = False) -> list[TestCase]:
    if client:
        try:
            raw = _parse_model_json(client.complete(
                prompt_prefix("generator", len(existing))
                + " " + json.dumps([r.model_dump() for r in requirements])
            ))
            if isinstance(raw, list):
                generated = _normalise_cases(raw, existing)
                if generated:
                    return generated
            raise ModelOutputError("Generator response contained no valid test cases.")
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            if not allow_fallback:
                raise ModelOutputError("Generator response did not match the test-case JSON contract.") from None
    cases = list(existing)
    used = {case.id for case in cases}
    covered = {req_id for case in cases for req_id in case.req_ids}
    for req in requirements:
        if req.id in covered:
            continue
        cases.append(TestCase(
            id=_unique_id("TC", used), req_ids=[req.id],
            title=f"Verify {req.text[:60]}",
            steps=["Open the application", "Perform the required action"],
            expected_result=req.text, type="positive", priority="high",
        ))
        cases.append(TestCase(
            id=_unique_id("TC", used), req_ids=[req.id],
            title=f"Reject invalid {req.text[:50]}",
            steps=["Open the application", "Provide invalid input"],
            expected_result="An actionable validation error is displayed",
            type="negative", priority="medium",
        ))
    return cases


def _critique(requirements: list[RequirementPoint], cases: list[TestCase],
              coverage, client: ModelClient | None,
              allow_fallback: bool = False) -> Critique:
    if client:
        try:
            data = _parse_model_json(client.complete(
                prompt_prefix("critic", len(cases)) + " " + json.dumps({
                    "requirements": [r.model_dump() for r in requirements],
                    "test_cases": [c.model_dump() for c in cases],
                    "coverage": coverage.model_dump(),
                })
            ))
            if isinstance(data, dict) and isinstance(data.get("feedback"), str):
                data["feedback"] = [data["feedback"]]
            return Critique.model_validate(data)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            if not allow_fallback:
                raise ModelOutputError("Critic response did not match the critique JSON contract.") from None
    score = min(1.0, coverage.score * (1.0 if cases else 0.0))
    feedback = [] if score >= 1 else ["Add cases for uncovered requirements and positive paths."]
    return Critique(score=score, coverage_score=coverage.score,
                    missing_req_ids=coverage.uncovered_requirement_ids
                    + coverage.missing_positive_requirement_ids, feedback=feedback)


def _generate_selenium_scripts(
    cases: list[TestCase],
    client: ModelClient | None,
    app_base_url: str,
    use_llm: bool = False,
    allow_fallback: bool = False,
) -> list[SeleniumScript]:
    if client and use_llm:
        try:
            response = _parse_model_json(client.complete(
                "Return only a JSON array with exactly one object for each input test case ID. "
                "Each object must contain test_case_id (copied exactly from the input), code "
                "(a string containing the complete pytest Selenium test), and locators (an "
                "array of objects with strategy and value string fields; use an empty array "
                "when no concrete locator is known). Locator strategy must be id, css selector, "
                "xpath, name, tag name, or link text. Do not return locators as prose or null. "
                "Generate pytest Selenium code using structured steps and expected results. "
                "Do not invent selectors or application-specific details; if the case lacks "
                "UI details, create an explicit pytest.fail limitation. Return valid JSON only, "
                "without Markdown fences or extra commentary. Test cases: "
                + json.dumps([case.model_dump(mode="json") for case in cases])
            ))
            if not isinstance(response, list):
                raise ModelOutputError("Selenium writer response must be a JSON array.")
            by_id: dict[str, dict] = {}
            for item in response:
                if not isinstance(item, dict):
                    raise ModelOutputError("Selenium writer returned a non-object artifact.")
                case_id = str(item.get("test_case_id", ""))
                if not case_id or case_id in by_id:
                    raise ModelOutputError("Selenium writer returned missing or duplicate test IDs.")
                by_id[case_id] = item
            expected_ids = {case.id for case in cases}
            if set(by_id) != expected_ids:
                raise ModelOutputError("Selenium writer did not return one script per test case.")
            return [
                SeleniumScript(
                    test_case_id=case.id,
                    filename=f"test_{case.id.lower()}.py",
                    code=str(by_id[case.id]["code"]),
                    locators=by_id[case.id].get("locators", []),
                )
                for case in cases
            ]
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            if not allow_fallback:
                raise ModelOutputError(
                    "Selenium writer response did not match the script JSON contract."
                ) from None
    return [
        SeleniumScript(
            test_case_id=case.id, filename=f"test_{case.id.lower()}.py",
            code=_script_for(case, app_base_url),
        )
        for case in cases
    ]


def _script_for(case: TestCase, app_base_url: str = "http://localhost:3000") -> str:
    lines = [
        f'"""Generated Selenium test for {case.id}."""',
        "import os",
        "import pytest",
        "from selenium import webdriver",
        "from selenium.webdriver.common.by import By",
        "from selenium.webdriver.support import expected_conditions as EC",
        "from selenium.webdriver.support.ui import WebDriverWait, Select",
        "",
        f"def test_{case.id.lower().replace('-', '_')}() -> None:",
        '    options = webdriver.ChromeOptions()',
        '    options.add_argument("--headless")',
        "    driver = webdriver.Chrome(options=options)",
        "    wait = WebDriverWait(driver, 10)",
        "    try:",
        f"        # Expected result: {case.expected_result.replace(chr(10), ' ')}",
    ]
    actions = list(case.actions)
    if not actions:
        lines += [
            f'        pytest.fail("Insufficient UI information for {case.id}: '
            'structured actions and locators are required")',
        ]
    for action in actions:
        if action.action == "navigate":
            target = action.value or "/"
            lines.append(
                f'        driver.get(os.environ.get("APP_BASE_URL", {app_base_url!r}).rstrip("/") + {target!r})'
            )
        elif action.locator is None:
            lines.append(f'        pytest.fail("Missing locator for {action.action}")')
        else:
            element = f"wait.until(EC.presence_of_element_located((By.{action.locator.strategy.replace(' ', '_').upper()}, {action.locator.value!r})))"
            if action.action == "click":
                lines.append(f"        wait.until(EC.element_to_be_clickable((By.{action.locator.strategy.replace(' ', '_').upper()}, {action.locator.value!r}))).click()")
            elif action.action == "fill":
                lines += [f"        element = {element}", "        element.clear()", f"        element.send_keys({action.value!r})"]
            elif action.action == "select":
                lines.append(f"        Select({element}).select_by_visible_text({action.value!r})")
            elif action.action == "assert_text":
                lines.append(f"        assert {action.expected!r} in {element}.text")
            elif action.action == "assert_visible":
                lines.append(f"        assert {element}.is_displayed()")
            elif action.action == "assert_url":
                lines.append(f"        assert {action.expected!r} in driver.current_url")
            elif action.action == "assert_element_count":
                lines.append(f"        assert len(driver.find_elements(By.{action.locator.strategy.replace(' ', '_').upper()}, {action.locator.value!r})) == {int(action.expected)}")
    lines += ["    finally:", "        driver.quit()", ""]
    return "\n".join(lines)


def validate_scripts(scripts: list[SeleniumScript]) -> ValidationReport:
    results: dict[str, list[str]] = {}
    errors: list[str] = []
    for script in scripts:
        messages: list[str] = []
        try:
            tree = ast.parse(script.code, filename=script.filename)
            has_test = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_") for node in ast.walk(tree)
            )
            has_assertion = any(isinstance(node, ast.Assert) for node in ast.walk(tree))
            has_failure = any(
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "pytest" and node.func.attr == "fail"
                for node in ast.walk(tree)
            )
            if not has_test:
                messages.append("missing pytest test function")
            if not has_assertion and not has_failure:
                messages.append("missing assertion or explicit limitation failure")
        except (SyntaxError, ValueError, TypeError) as exc:
            messages.append(f"{type(exc).__name__}: {exc}")
        results[script.filename] = messages or ["valid Python and pytest structure"]
        errors.extend(f"{script.filename}: {message}" for message in messages)
    rejected = sum(bool(messages) and messages != ["valid Python and pytest structure"]
                   for messages in results.values())
    return ValidationReport(
        valid=not errors, script_results=results, errors=errors,
        validated_count=len(scripts) - rejected, rejected_count=rejected,
    )


def export_suite(out_dir: Path, state: BlackboardState) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    script_dir = out_dir / "selenium_tests"
    script_dir.mkdir(exist_ok=True)
    ids = [case.id for case in state.test_cases]
    filenames = [script.filename for script in state.selenium_scripts]
    if len(ids) != len(set(ids)) or len(filenames) != len(set(filenames)):
        raise ValueError("Test-case IDs and Selenium filenames must be unique before export.")
    (out_dir / "test_cases.json").write_text(
        json.dumps([c.model_dump(mode="json") for c in state.test_cases], indent=2),
        encoding="utf-8",
    )
    rows = ["| ID | Requirements | Type | Title | Expected |", "|---|---|---|---|---|"]
    rows += [f"| {c.id} | {', '.join(c.req_ids)} | {c.type} | {c.title} | {c.expected_result} |"
             for c in state.test_cases]
    (out_dir / "test_cases.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    valid_files = set(state.validation_report.script_results) if state.validation_report else set()
    invalid_files = set(state.validation_report.errors if state.validation_report else [])
    for script in state.selenium_scripts:
        if state.validation_report and any(error.startswith(f"{script.filename}:") for error in invalid_files):
            continue
        if not state.validation_report or script.filename in valid_files:
            (script_dir / script.filename).write_text(script.code, encoding="utf-8")
    if state.run_report:
        (out_dir / "run_report.json").write_text(state.run_report.model_dump_json(indent=2), encoding="utf-8")


def run_pipeline(prd_path: Path, out_dir: Path, config: AppConfig | None = None,
                 clients: dict[str, ModelClient] | None = None, *,
                 run_id: str | None = None) -> BlackboardState:
    config = config or AppConfig()
    config.validate_runtime()
    clients = clients or {}
    required_clients = {"extractor", "generator", "critic"}
    if config.execution_mode == "llm" and not config.a2a_enabled:
        required_clients.add("selenium")
    if config.execution_mode == "llm" and not required_clients <= clients.keys():
        raise ValueError(
            "LLM mode is missing required model clients: "
            + ", ".join(sorted(required_clients - clients.keys()))
        )
    from .orchestration import create_orchestrator, make_context
    context = make_context(prd_path, out_dir, config, clients, run_id=run_id)
    context.monitor.emit("run_started", "started", metadata={"pattern": config.pipeline_pattern})
    try:
        return asyncio.run(create_orchestrator(config.pipeline_pattern).run(context))
    except Exception as exc:
        context.monitor.emit("run_failed", "failed", error_type=type(exc).__name__,
                             error_message=str(exc))
        context.monitor.finalize(False)
        raise


def build_adk_agents(config: AppConfig, monitor: Monitor | None = None):
    """Construct a native ADK topology with typed outputs and MCP tools."""
    from google.adk.agents import LlmAgent, ParallelAgent, SequentialAgent, LoopAgent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParams
    mcp_tools = MCPToolset(connection_params=StdioServerParams(
        command="python", args=["-m", "mcp_server.server"]))
    monitor = monitor or Monitor(
        Path(config.monitoring_dir), config.pipeline_pattern,
        enabled=config.monitoring_enabled,
        directory_name=config.monitoring_dir,
    )
    callbacks = build_adk_callbacks(monitor)

    def worker(name: str, role: str, output_schema: type[object]) -> LlmAgent:
        return LlmAgent(
            name=name,
            model=LiteLlm(
                model=config.models[role].name,
                api_base=config.ollama_base_url,
                timeout=config.model_timeout_seconds,
            ),
            instruction=(
                "Use tools when applicable. Return only JSON matching the "
                f"{name} contract and write it to the named output key."
            ),
            tools=[mcp_tools],
            output_schema=output_schema,
            output_key=name,
            **callbacks,
        )

    workers = {
        "document": worker("document", "extractor", Document),
        "chunks": worker("chunks", "extractor", Chunks),
        "requirement_points": worker(
            "requirement_points", "extractor", RequirementPoints
        ),
        "test_cases": worker("test_cases", "generator", TestCases),
        "critique": worker("critique", "critic", Critique),
    }
    if config.pipeline == "hierarchical":
        return LlmAgent(name="coordinator", model=LiteLlm(
            model=config.models["generator"].name,
            api_base=config.ollama_base_url,
            timeout=config.model_timeout_seconds,
        ), sub_agents=list(workers.values()), **callbacks)
    if config.pipeline == "parallel_fanout":
        return SequentialAgent(name="pipeline", sub_agents=[
            workers["document"], workers["chunks"],
            ParallelAgent(name="fanout", sub_agents=[
                workers["requirement_points"], workers["test_cases"],
            ]),
            workers["critique"],
        ])
    return SequentialAgent(name="pipeline", sub_agents=[
        workers["document"], workers["chunks"], workers["requirement_points"],
        LoopAgent(name="reflection", sub_agents=[
            workers["test_cases"], workers["critique"],
        ]),
    ])
