"""Reproducible deterministic comparison of the supported orchestration patterns."""
from __future__ import annotations

import csv
import json
import time
import uuid
from pathlib import Path

from .config import AppConfig
from .pipeline import run_pipeline


def compare_architectures(prd_path: Path, out_dir: Path, runs: int = 1,
                          base_config: AppConfig | None = None) -> Path:
    config = base_config or AppConfig(execution_mode="deterministic")
    rows: list[dict[str, object]] = []
    for pattern in ("sequential", "parallel", "hierarchical"):
        for index in range(runs):
            run_id = str(uuid.uuid4())
            started = time.monotonic()
            run_config = config.model_copy(update={
                "execution_mode": "deterministic",
                "pipeline_pattern": pattern,
                "monitoring_enabled": True,
            })
            try:
                state = run_pipeline(prd_path, out_dir / run_id, run_config, {})
                rows.append({
                    "run_id": run_id, "pattern": pattern, "run_number": index + 1,
                    "status": "completed",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "quality_score": state.run_report.final_quality_score if state.run_report else None,
                    "coverage_score": state.run_report.final_coverage_score if state.run_report else None,
                    "model_mode": run_config.execution_mode, "cached_responses": False,
                })
            except Exception as exc:
                rows.append({
                    "run_id": run_id, "pattern": pattern, "run_number": index + 1,
                    "status": "failed",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error": str(exc), "model_mode": run_config.execution_mode,
                    "cached_responses": False,
                })
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "architecture_comparison.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with (out_dir / "architecture_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = sorted({key for row in rows for key in row})
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    _write_comparison_charts(out_dir, rows)
    return json_path


def _write_comparison_charts(out_dir: Path, rows: list[dict[str, object]]) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    patterns = ["sequential", "parallel", "hierarchical"]
    durations = [
        [row["elapsed_seconds"] for row in rows
         if row["pattern"] == pattern and row["status"] == "completed"]
        for pattern in patterns
    ]
    durations = [values or [float("nan")] for values in durations]
    success = [
        sum(row["status"] == "completed" for row in rows if row["pattern"] == pattern)
        / max(1, sum(row["pattern"] == pattern for row in rows))
        for pattern in patterns
    ]
    fig, axis = plt.subplots(figsize=(7, 4))
    axis.boxplot(durations, labels=patterns)
    axis.set_ylabel("Wall-clock seconds")
    axis.set_title("Architecture duration comparison")
    fig.tight_layout()
    fig.savefig(out_dir / "comparison_duration.png")
    plt.close(fig)
    fig, axis = plt.subplots(figsize=(7, 3))
    image = axis.imshow([success], aspect="auto", cmap="YlGn")
    axis.set_xticks(range(len(patterns)), patterns)
    axis.set_yticks([0], ["success rate"])
    fig.colorbar(image, ax=axis, label="rate")
    fig.tight_layout()
    fig.savefig(out_dir / "comparison_heatmap.png")
    plt.close(fig)
