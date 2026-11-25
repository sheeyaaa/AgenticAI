"""Reproducible, sequential-only benchmark execution and reporting."""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import AppConfig
from .model_client import create_model_clients
from .pipeline import run_pipeline


class EvaluationConfig(BaseModel):
    scenarios_dir: Path = Path("samples/evaluation")
    output_dir: Path = Path("evaluation_results")
    repeats: int = Field(default=5, ge=1)
    browser_execution: bool = False
    input_token_price_per_million: float = Field(default=0.0, ge=0)
    output_token_price_per_million: float = Field(default=0.0, ge=0)
    max_iterations: int = Field(default=3, ge=1)
    seed: int = 0


class EvaluationResult(BaseModel):
    run_id: str
    scenario_id: str
    repeat: int
    started_at: str
    finished_at: str
    status: str
    error_type: str = ""
    error_message: str = ""
    total_latency_seconds: float
    stage_latency_seconds: dict[str, float] = Field(default_factory=dict)
    stage_failures: dict[str, int] = Field(default_factory=dict)
    requirement_count: int = 0
    test_case_count: int = 0
    coverage_score: float | None = None
    scripts_validated: int = 0
    scripts_rejected: int = 0
    script_validation_rate: float | None = None
    browser_status: str = "not_requested"
    browser_pass_rate: float | None = None
    retry_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cost_basis: str = "estimated_from_configured_prices"
    architecture: str = "blackboard"
    orchestration_pattern: str = "sequential"
    execution_mode: str = "deterministic"
    monitoring_events: int = 0


def scenario_paths(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.md"))


def _event_metrics(path: Path) -> tuple[dict[str, float], dict[str, int], int, int]:
    stage_latency: dict[str, float] = {}
    stage_failures: dict[str, int] = {}
    event_count = 0
    retries = 0
    if not path.exists():
        return stage_latency, stage_failures, event_count, retries
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        event_count += 1
        retries += int(event.get("retry_count", 0))
        if event.get("event_type") in {"agent_completed", "agent_failed"}:
            stage = str(event.get("agent_name") or "unknown")
            stage_latency[stage] = stage_latency.get(stage, 0.0) + (
                float(event.get("duration_ms") or 0.0) / 1000
            )
            if event.get("event_type") == "agent_failed":
                stage_failures[stage] = stage_failures.get(stage, 0) + 1
    return stage_latency, stage_failures, event_count, retries


def _browser_result(run_dir: Path) -> tuple[str, float | None]:
    scripts = sorted((run_dir / "selenium_tests").glob("test_*.py"))
    if not scripts:
        return "unavailable_no_scripts", None
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *[str(item) for item in scripts]],
        cwd=run_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    passed = sum(" passed" in line for line in completed.stdout.splitlines())
    failed = sum(" failed" in line for line in completed.stdout.splitlines())
    total = passed + failed
    if total == 0:
        return "unavailable_browser_or_driver", None
    return ("passed" if completed.returncode == 0 else "failed"), passed / total


def run_one(
    scenario: Path,
    repeat: int,
    config: EvaluationConfig,
    app_config: AppConfig,
) -> EvaluationResult:
    run_id = f"{scenario.stem}-{repeat:03d}-{uuid.uuid4().hex[:8]}"
    run_dir = config.output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    stage_latency: dict[str, float] = {}
    stage_failures: dict[str, int] = {}
    try:
        state = run_pipeline(
            scenario,
            run_dir,
            app_config,
            create_model_clients(app_config),
        )
        stage_latency, stage_failures, event_count, retries = _event_metrics(
            run_dir / app_config.monitoring_dir / "events.jsonl"
        )
        validation = state.validation_report
        browser_status = "not_requested"
        browser_rate: float | None = None
        if config.browser_execution:
            browser_status, browser_rate = _browser_result(run_dir)
        input_tokens = state.token_stats.get("input_tokens", 0)
        output_tokens = state.token_stats.get("output_tokens", 0)
        cost = (
            input_tokens * config.input_token_price_per_million
            + output_tokens * config.output_token_price_per_million
        ) / 1_000_000
        return EvaluationResult(
            run_id=run_id,
            scenario_id=scenario.stem,
            repeat=repeat,
            started_at=started_at.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            status="success",
            total_latency_seconds=time.perf_counter() - started,
            stage_latency_seconds=stage_latency,
            stage_failures=stage_failures,
            requirement_count=len(state.requirement_points),
            test_case_count=len(state.test_cases),
            coverage_score=state.coverage.score if state.coverage else None,
            scripts_validated=validation.validated_count if validation else 0,
            scripts_rejected=validation.rejected_count if validation else 0,
            script_validation_rate=(
                validation.validated_count / len(state.selenium_scripts)
                if validation and state.selenium_scripts else None
            ),
            browser_status=browser_status,
            browser_pass_rate=browser_rate,
            retry_count=retries,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            architecture=app_config.arch,
            orchestration_pattern=app_config.pipeline_pattern,
            execution_mode=app_config.execution_mode,
            monitoring_events=event_count,
        )
    except Exception as exc:
        event_path = run_dir / app_config.monitoring_dir / "events.jsonl"
        stage_latency, stage_failures, event_count, retries = _event_metrics(event_path)
        return EvaluationResult(
            run_id=run_id,
            scenario_id=scenario.stem,
            repeat=repeat,
            started_at=started_at.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            status="failure",
            error_type=type(exc).__name__,
            error_message=str(exc),
            total_latency_seconds=time.perf_counter() - started,
            stage_latency_seconds=stage_latency,
            stage_failures=stage_failures,
            retry_count=retries,
            architecture=app_config.arch,
            orchestration_pattern=app_config.pipeline_pattern,
            execution_mode=app_config.execution_mode,
            monitoring_events=event_count,
        )


def _completed_keys(path: Path) -> set[tuple[str, int]]:
    if not path.exists():
        return set()
    return {
        (item["scenario_id"], int(item["repeat"]))
        for item in (json.loads(line) for line in path.read_text().splitlines() if line)
    }


def run_evaluation(config: EvaluationConfig) -> Path:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = config.output_dir / "raw_results.jsonl"
    completed = _completed_keys(raw_path)
    app_config = AppConfig(
        pipeline_pattern="sequential",
        pipeline="sequential_loop",
        max_iterations=config.max_iterations,
        arch="blackboard",
    )
    app_config.validate_runtime()
    scenarios = scenario_paths(config.scenarios_dir)
    if not scenarios:
        raise FileNotFoundError(f"No evaluation PRDs found in {config.scenarios_dir}")
    with raw_path.open("a", encoding="utf-8") as handle:
        for scenario in scenarios:
            for repeat in range(1, config.repeats + 1):
                if (scenario.stem, repeat) in completed:
                    continue
                result = run_one(scenario, repeat, config, app_config)
                handle.write(result.model_dump_json() + "\n")
                handle.flush()
    write_reports(config, raw_path)
    return raw_path


def _load_results(path: Path) -> list[EvaluationResult]:
    return [
        EvaluationResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(results: list[EvaluationResult]) -> dict[str, Any]:
    latencies = [result.total_latency_seconds for result in results]
    successes = sum(result.status == "success" for result in results)
    costs = [result.estimated_cost_usd for result in results]
    stage_latency: dict[str, float] = {}
    stage_failures: dict[str, int] = {}
    for result in results:
        for stage, latency in result.stage_latency_seconds.items():
            stage_latency[stage] = stage_latency.get(stage, 0.0) + latency
        for stage, count in result.stage_failures.items():
            stage_failures[stage] = stage_failures.get(stage, 0) + count
    return {
        "runs": len(results),
        "successes": successes,
        "failures": len(results) - successes,
        "success_rate": successes / len(results) if results else None,
        "latency_seconds": {
            "mean": statistics.mean(latencies) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
            "stdev": statistics.stdev(latencies) if len(latencies) > 1 else 0.0,
            "p95": _percentile(latencies, 0.95),
        },
        "throughput_runs_per_second": (
            len(results) / sum(latencies) if sum(latencies) else None
        ),
        "cost": {
            "measured_or_estimated": "estimated",
            "total_usd": sum(costs),
            "per_prd_usd": sum(costs) / len(results) if results else None,
            "projected_100_prds_usd": (
                sum(costs) / len(results) * 100 if results else None
            ),
            "projected_1000_prds_usd": (
                sum(costs) / len(results) * 1000 if results else None
            ),
        },
        "coverage": {
            "mean": statistics.mean(
                [item.coverage_score for item in results if item.coverage_score is not None]
            ) if any(item.coverage_score is not None for item in results) else None,
            "script_validation_rate": statistics.mean(
                [item.script_validation_rate for item in results
                 if item.script_validation_rate is not None]
            ) if any(item.script_validation_rate is not None for item in results) else None,
        },
        "stage_latency_seconds_total": dict(sorted(
            stage_latency.items(), key=lambda item: item[1], reverse=True
        )),
        "stage_failure_counts": dict(sorted(
            stage_failures.items(), key=lambda item: item[1], reverse=True
        )),
    }


def write_reports(config: EvaluationConfig, raw_path: Path) -> None:
    import pandas as pd

    results = _load_results(raw_path)
    summary = summarize(results)
    report_dir = config.output_dir / "reports"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    rows = [item.model_dump(mode="json") for item in results]
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["stage_latency_seconds"] = frame["stage_latency_seconds"].map(json.dumps)
        frame["stage_failures"] = frame["stage_failures"].map(json.dumps)
    frame.to_csv(config.output_dir / "results.csv", index=False)
    _write_plots(results, report_dir)
    _write_markdown_report(results, summary, report_dir)
    (config.output_dir / "experiment_config.json").write_text(
        json.dumps({
            "evaluation": config.model_dump(mode="json"),
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
                "cwd": str(Path.cwd()),
                "pid": os.getpid(),
            },
            "sequential_only": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2), encoding="utf-8",
    )


def _write_plots(results: list[EvaluationResult], directory: Path) -> None:
    import pandas as pd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    latencies = [item.total_latency_seconds for item in results]
    plt.figure(figsize=(8, 4))
    plt.hist(latencies, bins=min(15, max(1, len(latencies))), color="steelblue")
    plt.xlabel("Runtime (seconds)")
    plt.ylabel("Runs")
    plt.title("Runtime distribution")
    plt.tight_layout()
    plt.savefig(directory / "runtime_distribution.png")
    plt.close()

    statuses = {"success": sum(item.status == "success" for item in results),
                "failure": sum(item.status == "failure" for item in results)}
    plt.figure(figsize=(6, 4))
    plt.bar(statuses.keys(), statuses.values(), color=["seagreen", "indianred"])
    plt.title("Success and failure counts")
    plt.tight_layout()
    plt.savefig(directory / "success_failure.png")
    plt.close()

    stage_totals: dict[str, float] = {}
    for item in results:
        for stage, latency in item.stage_latency_seconds.items():
            stage_totals[stage] = stage_totals.get(stage, 0.0) + latency
    plt.figure(figsize=(9, 4))
    plt.bar(stage_totals.keys(), stage_totals.values(), color="darkorange")
    plt.ylabel("Cumulative seconds")
    plt.title("Stage-wise latency and bottlenecks")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(directory / "stage_latency.png")
    plt.close()

    frame = pd.DataFrame([item.model_dump(mode="json") for item in results])
    by_scenario = {
        scenario: group["total_latency_seconds"].tolist()
        for scenario, group in frame.groupby("scenario_id")
    } if not frame.empty else {}
    plt.figure(figsize=(10, 4))
    plt.boxplot(by_scenario.values(), tick_labels=by_scenario.keys())
    plt.ylabel("Seconds")
    plt.title("Performance by PRD scenario")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(directory / "scenario_performance.png")
    plt.close()

    plt.figure(figsize=(8, 4))
    plt.plot(range(1, len(latencies) + 1), latencies, marker=".", color="purple")
    plt.xlabel("Completed run order")
    plt.ylabel("Seconds")
    plt.title("Run-to-run variability")
    plt.tight_layout()
    plt.savefig(directory / "run_variability.png")
    plt.close()

    failures = frame.loc[frame["status"] == "failure", "error_type"].fillna(
        "unknown"
    ).value_counts().to_dict() if not frame.empty else {}
    plt.figure(figsize=(8, 4))
    plt.bar(failures.keys() or ["none"], failures.values() or [0], color="crimson")
    plt.title("Failure counts by pipeline stage/error")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.savefig(directory / "failure_counts.png")
    plt.close()


def _write_markdown_report(
    results: list[EvaluationResult], summary: dict[str, Any], directory: Path
) -> None:
    lines = [
        "# Sequential Agentic AI Evaluation Report",
        "",
        "This report contains only sequential, deterministic pipeline executions.",
        "Browser results are marked unavailable unless explicitly requested and executed.",
        "",
        "## Summary",
        "",
        f"- Runs: {summary['runs']}",
        f"- Success rate: {summary['success_rate']}",
        f"- Mean latency: {summary['latency_seconds']['mean']} seconds",
        f"- Median latency: {summary['latency_seconds']['median']} seconds",
        f"- P95 latency: {summary['latency_seconds']['p95']} seconds",
        f"- Throughput: {summary['throughput_runs_per_second']} runs/second",
        f"- Estimated cost per PRD: {summary['cost']['per_prd_usd']} USD",
        f"- Projected cost for 100 PRDs: {summary['cost']['projected_100_prds_usd']} USD",
        f"- Projected cost for 1,000 PRDs: {summary['cost']['projected_1000_prds_usd']} USD",
        "",
        "## Key findings",
        "",
        f"- Measured sequential success rate: {summary['success_rate']}.",
        f"- Measured p95 runtime: {summary['latency_seconds']['p95']} seconds.",
        "- Deterministic runs produced no provider token usage; cost is estimated "
        "from configured pricing and is zero with the default prices.",
        "- Browser execution was not requested; no browser test was counted as passed.",
        "",
        "## Stage latency totals",
        "",
        *[
            f"- `{stage}`: {seconds:.6f} seconds"
            for stage, seconds in summary["stage_latency_seconds_total"].items()
        ],
        "",
        "## Recommendations",
        "",
        "- Repeat with `--browser` in an environment with Chrome and ChromeDriver "
        "to measure actual browser pass rates.",
        "- Run LLM mode with explicit input/output prices to replace zero "
        "deterministic cost estimates with configured estimates.",
        "- Investigate the highest cumulative stage latency before scaling to larger "
        "PRD volumes.",
        "",
        "## Graphs",
        "",
    ]
    for filename in (
        "runtime_distribution.png", "success_failure.png", "stage_latency.png",
        "scenario_performance.png", "run_variability.png", "failure_counts.png",
    ):
        lines.append(f"![{filename}](./{filename})")
        lines.append("")
    lines.extend([
        "## Limitations",
        "",
        "- Deterministic mode does not produce provider token usage; token and cost values are estimates.",
        "- Browser execution is not counted unless explicitly requested and a browser/driver is available.",
        "- No skipped or unexecuted browser test is counted as a pass.",
    ])
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run sequential PRD evaluation.")
    parser.add_argument("--scenarios", type=Path, default=Path("samples/evaluation"))
    parser.add_argument("--out", type=Path, default=Path("evaluation_results"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--input-price", type=float, default=0.0)
    parser.add_argument("--output-price", type=float, default=0.0)
    parser.add_argument("--max-iterations", type=int, default=3)
    args = parser.parse_args()
    result = run_evaluation(EvaluationConfig(
        scenarios_dir=args.scenarios,
        output_dir=args.out,
        repeats=args.repeats,
        browser_execution=args.browser,
        input_token_price_per_million=args.input_price,
        output_token_price_per_million=args.output_price,
        max_iterations=args.max_iterations,
    ))
    print(f"Raw results: {result}")
    print(f"Report: {args.out / 'reports' / 'report.md'}")


if __name__ == "__main__":
    main()
