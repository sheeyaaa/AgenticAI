from pathlib import Path
import argparse
from .config import AppConfig
from .benchmark import benchmark_models
from .model_client import create_model_clients
from .pipeline import run_pipeline
from .guardrails import GuardrailViolation


def sample_paths() -> list[Path]:
    return sorted(Path(__file__).parent.parent.joinpath("samples").glob("*.md"))


def choose_sample() -> Path:
    samples = sample_paths()
    if not samples:
        raise FileNotFoundError("No Markdown PRD samples were found in the samples directory.")
    print("Available sample PRDs:")
    for index, sample in enumerate(samples, 1):
        print(f"  {index}. {sample.stem}")
    while True:
        choice = input(f"Choose a sample PRD [1-{len(samples)}]: ").strip()
        try:
            selected = int(choice)
        except ValueError:
            selected = 0
        if 1 <= selected <= len(samples):
            return samples[selected - 1]
        print(f"Please enter a number from 1 to {len(samples)}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prd", type=Path, nargs="?", help="PRD path; omit to choose a sample interactively")
    parser.add_argument("--list-samples", action="store_true", help="List bundled sample PRDs and exit")
    parser.add_argument("--benchmark-models", action="store_true", help="Test all generator/critic Ollama pairings")
    parser.add_argument("--compare-architectures", action="store_true",
                        help="Run the deterministic architecture comparison experiment")
    parser.add_argument("--runs", type=int, default=1, help="Runs per pattern for comparison")
    parser.add_argument("--pattern", choices=["sequential", "parallel", "hierarchical"],
                        help="Orchestration pattern; overrides PIPELINE_PATTERN")
    parser.add_argument("--max-parallel-agents", type=int)
    parser.add_argument("--max-hierarchy-cycles", type=int)
    parser.add_argument("--disable-monitoring", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("output"))
    args = parser.parse_args()
    if args.list_samples:
        for sample in sample_paths():
            print(sample.stem)
        return
    prd = args.prd or choose_sample()
    base_config = AppConfig()
    if args.compare_architectures:
        from .experiment import compare_architectures
        report = compare_architectures(prd, args.out, max(1, args.runs), base_config)
        print(f"Architecture comparison report: {report}")
        return
    if args.benchmark_models:
        report = benchmark_models(prd, args.out, base_config.ollama_base_url)
        print(f"Benchmark report: {report}")
        return
    overrides = {}
    if args.pattern:
        overrides["pipeline_pattern"] = args.pattern
    if args.max_parallel_agents is not None:
        overrides["max_parallel_agents"] = args.max_parallel_agents
    if args.max_hierarchy_cycles is not None:
        overrides["max_hierarchy_cycles"] = args.max_hierarchy_cycles
    if args.disable_monitoring:
        overrides["monitoring_enabled"] = False
    config = base_config.model_copy(update=overrides)
    clients = create_model_clients(config)
    try:
        run_pipeline(prd, args.out, config, clients)
    except GuardrailViolation as exc:
        print(f"ERROR: {exc}", flush=True)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
