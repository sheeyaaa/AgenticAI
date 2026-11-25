"""Sequential, dependency-aware parallel, and coordinator-led orchestration."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .blackboard import Blackboard
from .config import AppConfig
from .coverage import check_coverage
from .document import chunk_document, parse_document
from .models import (
    Critique, IterationRecord, RunReport, SeleniumScript, TestCase,
)
from .monitoring import Monitor
from .guardrails import GuardrailViolation, validate_document


@dataclass
class PipelineContext:
    prd_path: Path
    out_dir: Path
    config: AppConfig
    clients: dict[str, Any]
    monitor: Monitor
    blackboard: "StateBackend"
    started: float


class StateBackend(Protocol):
    def read(self, key: str) -> Any: ...
    def write(self, agent: str, key: str, value: Any) -> None: ...
    def snapshot(self): ...


class Orchestrator:
    async def run(self, context: PipelineContext):
        raise NotImplementedError


def _call(context: PipelineContext, name: str, dependencies: list[str],
          function: Callable[[], Any], parent: str = "") -> Any:
    context.monitor.start_agent(name, dependencies, parent)
    try:
        value = function()
    except Exception as exc:
        context.monitor.finish_agent(name, "failed", error=exc)
        raise
    context.monitor.finish_agent(name, output_summary=type(value).__name__)
    return value


def _prepare(context: PipelineContext) -> list:
    document = _call(context, "ingest", [], lambda: parse_document(context.prd_path))
    guardrail_report = validate_document(document)
    context.monitor.validation_result(
        "guardrails",
        guardrail_report.allowed,
        metadata={
            "allowed": guardrail_report.allowed,
            "finding_count": len(guardrail_report.findings),
            "categories": sorted({item.category for item in guardrail_report.findings}),
        },
    )
    if not guardrail_report.allowed:
        raise GuardrailViolation(guardrail_report)
    context.blackboard.write("ingest", "document", document)
    chunks = _call(
        context, "chunker", ["ingest"],
        lambda: chunk_document(document, context.config.chunk_size_tokens,
                                context.config.chunk_overlap_tokens),
    )
    context.blackboard.write("chunker", "chunks", chunks)
    from .pipeline import _extract_requirements
    requirements = _call(
        context, "extractor", ["chunker"],
        lambda: _extract_requirements(
            chunks, context.clients.get("extractor"), context.config.allow_fallback
        ),
    )
    context.blackboard.write("extractor", "requirement_points", requirements)
    return requirements


def _generate(context: PipelineContext, requirements: list, parent: str = "") -> list[TestCase]:
    from .pipeline import _generate_cases
    existing = context.blackboard.snapshot().test_cases
    cases = _call(
        context, "generator", ["extractor"], lambda: _generate_cases(
            requirements, existing, context.clients.get("generator"),
            context.config.allow_fallback), parent,
    )
    context.blackboard.write("generator", "test_cases", cases)
    context.blackboard.write("generator", "iteration",
                             context.blackboard.snapshot().iteration + 1)
    return cases


def _review(context: PipelineContext, requirements: list, cases: list[TestCase],
            parent: str = "") -> tuple[Any, Critique]:
    from .pipeline import _critique
    coverage = check_coverage(requirements, cases)
    critique = _call(
        context, "critic", ["generator"], lambda: _critique(
            requirements, cases, coverage, context.clients.get("critic"),
            context.config.allow_fallback), parent,
    )
    return coverage, critique


def _record_review(context: PipelineContext, coverage: Any, critique: Critique) -> None:
    context.blackboard.write("coverage_checker", "coverage", coverage)
    previous = context.blackboard.snapshot()
    stale = previous.stale_iterations + 1 if (
        previous.history and critique.score <= max(item.score for item in previous.history)
    ) else 0
    context.blackboard.write("critic", "critique", critique)
    context.blackboard.write("critic", "stale_iterations", stale)
    context.blackboard.write("critic", "history", previous.history + [IterationRecord(
        iteration=previous.iteration, score=critique.score,
        coverage_score=critique.coverage_score, test_cases=previous.test_cases,
        critique=critique,
    )])


def _finish(context: PipelineContext, requirements: list, cases: list[TestCase]):
    from .pipeline import export_suite, validate_scripts, _generate_selenium_scripts
    def generate_scripts() -> list[SeleniumScript]:
        if context.config.a2a_enabled:
            from a2a_service.client import submit_test_cases
            return [
                SeleniumScript.model_validate(item)
                for item in submit_test_cases(
                    context.config.a2a_url,
                    [case.model_dump(mode="json") for case in cases],
                )
            ]
        return _generate_selenium_scripts(
            cases,
            context.clients.get("selenium"),
            context.config.app_base_url,
            use_llm=context.config.execution_mode == "llm",
            allow_fallback=context.config.allow_fallback,
        )

    scripts = _call(context, "selenium_script_generator", ["critic"], generate_scripts)
    context.blackboard.write("selenium_script_generator", "selenium_scripts", scripts)
    validation = _call(context, "script_validator", ["selenium_script_generator"],
                       lambda: validate_scripts(scripts))
    context.blackboard.write("script_validator", "validation_report", validation)
    if validation.valid:
        context.monitor.emit("validation_passed", "completed", "script_validator")
    else:
        context.monitor.emit("validation_failed", "failed", "script_validator",
                             output_summary=str(validation.errors))
    state = context.blackboard.snapshot()
    provider_usage = {
        role: client.usage_summary
        for role, client in context.clients.items()
        if isinstance(getattr(client, "usage_summary", None), dict)
        and client.usage_summary.get("calls", 0) > 0
    }
    all_usage_available = bool(provider_usage) and all(
        item["usage_available"] for item in provider_usage.values()
    )
    estimated_tokens = (
        {
            "input_tokens": sum(item["input_tokens"] for item in provider_usage.values()),
            "output_tokens": sum(item["output_tokens"] for item in provider_usage.values()),
        }
        if all_usage_available else ({} if provider_usage else state.token_stats)
    )
    estimated_cost = (
        sum(item["estimated_cost_usd"] for item in provider_usage.values())
        if all_usage_available and all(
            item["estimated_cost_usd"] is not None for item in provider_usage.values()
        ) else None
    )
    if all_usage_available:
        context.blackboard.write("usage_tracker", "token_stats", estimated_tokens)
    for role, usage in provider_usage.items():
        context.monitor.emit(
            "model_usage_recorded", "completed", role,
            metadata={
                "provider": usage["provider"],
                "model": usage["model"],
                "calls": usage["calls"],
                "input_tokens": usage["input_tokens"],
                "output_tokens": usage["output_tokens"],
                "estimated_cost_usd": usage["estimated_cost_usd"],
            },
        )
    state = context.blackboard.snapshot()
    report = RunReport(
        run_id=context.monitor.run_id,
        source_path=str(context.prd_path),
        iterations=state.iteration,
        final_quality_score=state.critique.score if state.critique else 0,
        final_coverage_score=state.coverage.score if state.coverage else 0,
        deterministic_coverage_percent=state.coverage.score * 100 if state.coverage else 0,
        remaining_gaps={
            "uncovered_requirement_ids": state.coverage.uncovered_requirement_ids if state.coverage else [],
            "missing_positive_requirement_ids": state.coverage.missing_positive_requirement_ids if state.coverage else [],
            "missing_negative_requirement_ids": state.coverage.missing_negative_requirement_ids if state.coverage else [],
        },
        requirement_count=len(requirements), test_case_count=len(cases),
        script_count=len(scripts), scripts_validated=validation.validated_count,
        scripts_rejected=validation.rejected_count,
        elapsed_seconds=round(time.monotonic() - context.started, 3),
        estimated_token_counts=estimated_tokens,
        provider_usage=provider_usage,
        estimated_api_cost_usd=estimated_cost,
        execution_mode=context.config.execution_mode,
        architecture=context.config.arch,
        orchestration_pattern=context.config.pipeline_pattern,
        effective_config={
            "max_parallel_agents": context.config.max_parallel_agents,
            "max_hierarchy_cycles": context.config.max_hierarchy_cycles,
            "monitoring_enabled": context.config.monitoring_enabled,
        },
        models_used={role: setting.name for role, setting in context.config.models.items()}
        if context.config.execution_mode == "llm" else {},
        diagnostics=validation.errors,
    )
    context.blackboard.write("exporter", "run_report", report)
    state = context.blackboard.snapshot()
    export_suite(context.out_dir, state)
    context.monitor.finalize(validation.valid)
    return state


class SequentialOrchestrator(Orchestrator):
    async def run(self, context: PipelineContext):
        requirements = _prepare(context)
        for _ in range(context.config.max_iterations):
            cases = _generate(context, requirements)
            coverage, critique = _review(context, requirements, cases)
            _record_review(context, coverage, critique)
            state = context.blackboard.snapshot()
            if (critique.score >= context.config.quality_threshold
                    and coverage.score >= context.config.coverage_target) or state.stale_iterations >= 2:
                break
        return _finish(context, requirements, context.blackboard.snapshot().test_cases)


class ParallelOrchestrator(Orchestrator):
    async def run(self, context: PipelineContext):
        requirements = _prepare(context)
        semaphore = asyncio.Semaphore(context.config.max_parallel_agents)
        for _ in range(context.config.max_iterations):
            cases = _generate(context, requirements)

            async def coverage_task():
                async with semaphore:
                    context.monitor.start_agent("coverage_checker", ["generator"])
                    try:
                        result = await asyncio.to_thread(check_coverage, requirements, cases)
                    except Exception as exc:
                        context.monitor.finish_agent("coverage_checker", "failed", error=exc)
                        raise
                    context.monitor.finish_agent("coverage_checker",
                                                 output_summary="CoverageReport")
                    return result

            async def critic_task():
                async with semaphore:
                    from .pipeline import _critique
                    context.monitor.start_agent("critic", ["generator"])
                    try:
                        result = await asyncio.to_thread(
                            _critique, requirements, cases,
                            check_coverage(requirements, cases),
                            context.clients.get("critic"),
                        )
                    except Exception as exc:
                        context.monitor.finish_agent("critic", "failed", error=exc)
                        raise
                    context.monitor.finish_agent("critic", output_summary="Critique")
                    return result

            coverage, critique = await asyncio.gather(coverage_task(), critic_task())
            _record_review(context, coverage, critique)
            state = context.blackboard.snapshot()
            if (critique.score >= context.config.quality_threshold
                    and coverage.score >= context.config.coverage_target) or state.stale_iterations >= 2:
                break
        return _finish(context, requirements, context.blackboard.snapshot().test_cases)


class HierarchicalOrchestrator(Orchestrator):
    async def run(self, context: PipelineContext):
        coordinator = "coordinator"
        requirements = _prepare(context)
        context.monitor.emit("task_delegated", "started", coordinator,
                             parent_agent=coordinator,
                             metadata={"workers": ["generator", "critic", "script_validator"]})
        for cycle in range(context.config.max_hierarchy_cycles + 1):
            cases = _generate(context, requirements, coordinator)
            coverage, critique = _review(context, requirements, cases, coordinator)
            _record_review(context, coverage, critique)
            if (critique.score >= context.config.quality_threshold
                    and coverage.score >= context.config.coverage_target):
                context.monitor.emit("review_completed", "completed", coordinator,
                                     metadata={"cycle": cycle})
                break
            if cycle < context.config.max_hierarchy_cycles:
                context.monitor.emit("revision_requested", "started", coordinator,
                                     metadata={"cycle": cycle, "reason": critique.feedback})
        return _finish(context, requirements, context.blackboard.snapshot().test_cases)


def create_orchestrator(pattern: str) -> Orchestrator:
    return {
        "sequential": SequentialOrchestrator(),
        "parallel": ParallelOrchestrator(),
        "hierarchical": HierarchicalOrchestrator(),
    }[pattern]


def make_context(prd_path: Path, out_dir: Path, config: AppConfig,
                 clients: dict[str, Any], run_id: str | None = None) -> PipelineContext:
    monitor = Monitor(out_dir, config.pipeline_pattern, config.monitoring_enabled,
                      config.event_log_verbosity,
                      run_id=run_id, directory_name=config.monitoring_dir)
    if config.arch == "message_passing":
        from messaging.message_bus import MessagePassingState
        blackboard = MessagePassingState()
    else:
        blackboard = Blackboard(monitor=monitor)
    return PipelineContext(
        prd_path=prd_path, out_dir=out_dir, config=config, clients=clients,
        monitor=monitor, blackboard=blackboard,
        started=time.monotonic(),
    )
