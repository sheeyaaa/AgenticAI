"""Benchmark generator/critic Ollama pairings on a bundled PRD."""
from __future__ import annotations
import json
import time
from pathlib import Path
from .config import AppConfig
from .model_client import OllamaClient
from .pipeline import ModelClient, run_pipeline

MODEL_NAMES = (
    "ollama/mistral:7b-instruct",
    "ollama/llama3.1:8b",
    "ollama/qwen2.5:7b-instruct",
)


def benchmark_models(prd_path: Path, out_dir: Path, base_url: str = "http://localhost:11434") -> Path:
    results: list[dict[str, object]] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    report = out_dir / "model_benchmark.json"
    for generator in MODEL_NAMES:
        for critic in MODEL_NAMES:
            started = time.monotonic()
            print(f"[benchmark] generator={generator} critic={critic}", flush=True)
            config = AppConfig(
                max_iterations=1,
                quality_threshold=1.0,
                coverage_target=1.0,
                ollama_base_url=base_url,
                execution_mode="llm",
            )
            clients: dict[str, ModelClient] = {
                "extractor": OllamaClient(generator, base_url),
                "generator": OllamaClient(generator, base_url),
                "critic": OllamaClient(critic, base_url),
                "selenium": OllamaClient(generator, base_url),
            }
            try:
                generator_slug = generator.replace("/", "_").replace(":", "_")
                critic_slug = critic.replace("/", "_").replace(":", "_")
                state = run_pipeline(prd_path, out_dir / f"{generator_slug}__{critic_slug}",
                                     config, clients)
                results.append({
                    "generator": generator, "critic": critic,
                    "quality_score": state.critique.score if state.critique else 0,
                    "coverage_score": state.coverage.score if state.coverage else 0,
                    "test_case_count": len(state.test_cases),
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "status": "ok",
                })
            except Exception as exc:
                results.append({
                    "generator": generator, "critic": critic,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "status": "error", "error": str(exc),
                })
            report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return report
