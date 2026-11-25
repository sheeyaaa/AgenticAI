"""Environment-backed application and per-agent model configuration."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr
from typing import Literal

load_dotenv()

Provider = Literal["ollama", "gemini", "groq"]
_DEFAULT_MODELS = {
    "extractor": "ollama/llama3.1:8b",
    "generator": "ollama/qwen2.5:7b-instruct",
    "critic": "ollama/mistral:7b-instruct",
    "selenium": "ollama/qwen2.5:7b-instruct",
}
_PROVIDERS: set[str] = {"ollama", "gemini", "groq"}


def _optional_float(name: str) -> float | None:
    value = os.getenv(name)
    return float(value) if value else None


def _model_setting(role: str, default_model: str) -> "ModelSetting":
    prefix = role.upper()
    model_value = os.getenv(f"{prefix}_MODEL", default_model).strip()
    inferred_provider = (
        model_value.split("/", 1)[0].lower()
        if "/" in model_value and model_value.split("/", 1)[0].lower() in _PROVIDERS
        else "ollama"
    )
    provider = (os.getenv(f"{prefix}_PROVIDER") or inferred_provider).strip().lower()
    if model_value.lower().startswith(provider + "/"):
        model_value = model_value[len(provider) + 1:]
    role_key_ref = f"{prefix}_API_KEY"
    provider_key_ref = f"{provider.upper()}_API_KEY"
    configured_key_ref = os.getenv(f"{prefix}_API_KEY_REF")
    api_key_ref = (
        role_key_ref if os.getenv(role_key_ref)
        else configured_key_ref if configured_key_ref
        else provider_key_ref if os.getenv(provider_key_ref)
        else None
    )
    api_key = os.getenv(api_key_ref) if api_key_ref else None

    fallback_provider = (
        os.getenv(f"{prefix}_FALLBACK_PROVIDER") or provider
    ).strip().lower()
    fallback_model = os.getenv(f"{prefix}_FALLBACK_MODEL") or None
    fallback_key = (
        os.getenv(f"{prefix}_FALLBACK_API_KEY")
        or os.getenv(f"{fallback_provider.upper()}_API_KEY")
    )
    return ModelSetting(
        provider=provider,
        name=model_value,
        api_key=SecretStr(api_key) if api_key else None,
        credential_ref=api_key_ref,
        fallback_provider=fallback_provider if fallback_model else None,
        fallback_model=fallback_model,
        fallback_api_key=SecretStr(fallback_key) if fallback_key else None,
        input_cost_per_million_tokens=_optional_float(
            f"{prefix}_INPUT_COST_PER_MILLION_TOKENS"
        ),
        output_cost_per_million_tokens=_optional_float(
            f"{prefix}_OUTPUT_COST_PER_MILLION_TOKENS"
        ),
        fallback_input_cost_per_million_tokens=_optional_float(
            f"{prefix}_FALLBACK_INPUT_COST_PER_MILLION_TOKENS"
        ),
        fallback_output_cost_per_million_tokens=_optional_float(
            f"{prefix}_FALLBACK_OUTPUT_COST_PER_MILLION_TOKENS"
        ),
    )


class ModelSetting(BaseModel):
    provider: Provider = "ollama"
    name: str
    api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    credential_ref: str | None = Field(default=None, exclude=True, repr=False)
    fallback_provider: Provider | None = None
    fallback_model: str | None = None
    fallback_api_key: SecretStr | None = Field(default=None, exclude=True, repr=False)
    input_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    output_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    fallback_input_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    fallback_output_cost_per_million_tokens: float | None = Field(default=None, ge=0)


class AppConfig(BaseModel):
    ollama_base_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    models: dict[str, ModelSetting] = Field(default_factory=lambda: {
        role: _model_setting(role, model) for role, model in _DEFAULT_MODELS.items()
    })
    quality_threshold: float = float(os.getenv("QUALITY_THRESHOLD", "0.8"))
    coverage_target: float = float(os.getenv("COVERAGE_TARGET", "0.9"))
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "3"))
    chunk_size_tokens: int = int(os.getenv("CHUNK_SIZE_TOKENS", "800"))
    chunk_overlap_tokens: int = int(os.getenv("CHUNK_OVERLAP_TOKENS", "80"))
    arch: str = os.getenv("ARCH", "blackboard")
    pipeline: str = os.getenv("PIPELINE", "sequential_loop")
    a2a_url: str = os.getenv("A2A_URL", "http://127.0.0.1:8081")
    a2a_enabled: bool = os.getenv("A2A_ENABLED", "false").lower() == "true"
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:3000")
    execution_mode: str = os.getenv("EXECUTION_MODE", "deterministic")
    allow_fallback: bool = os.getenv("ALLOW_FALLBACK", "false").lower() == "true"
    model_timeout_seconds: float = float(os.getenv("MODEL_TIMEOUT_SECONDS", "300"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "2"))
    model_retry_base_seconds: float = float(os.getenv("MODEL_RETRY_BASE_SECONDS", "1"))
    model_retry_max_seconds: float = float(os.getenv("MODEL_RETRY_MAX_SECONDS", "8"))
    pipeline_pattern: str = os.getenv("PIPELINE_PATTERN", "sequential")
    max_parallel_agents: int = int(os.getenv("MAX_PARALLEL_AGENTS", "2"))
    max_hierarchy_cycles: int = int(os.getenv("MAX_HIERARCHY_CYCLES", "2"))
    monitoring_enabled: bool = os.getenv("MONITORING_ENABLED", "true").lower() == "true"
    monitoring_dir: str = os.getenv("MONITORING_DIR", "monitoring")
    event_log_verbosity: str = os.getenv("EVENT_LOG_VERBOSITY", "normal")

    def validate_runtime(self) -> None:
        if self.execution_mode not in {"deterministic", "llm"}:
            raise ValueError("EXECUTION_MODE must be 'deterministic' or 'llm'.")
        if self.arch not in {"blackboard", "message_passing"}:
            raise ValueError(
                f"Unsupported ARCH={self.arch!r}; supported architectures: "
                "'blackboard' and 'message_passing'."
            )
        if self.pipeline not in {"sequential_loop", "hierarchical", "parallel_fanout"}:
            raise ValueError(
                f"Unsupported PIPELINE={self.pipeline!r}; choose sequential_loop, "
                "hierarchical, or parallel_fanout."
            )
        if not self.app_base_url.startswith(("http://", "https://")):
            raise ValueError("APP_BASE_URL must start with http:// or https://.")
        if self.model_timeout_seconds <= 0:
            raise ValueError("MODEL_TIMEOUT_SECONDS must be greater than zero.")
        if self.model_max_retries < 0:
            raise ValueError("MODEL_MAX_RETRIES cannot be negative.")
        if self.model_retry_base_seconds < 0 or self.model_retry_max_seconds < 0:
            raise ValueError("Model retry backoff values cannot be negative.")
        if self.pipeline_pattern not in {"sequential", "parallel", "hierarchical"}:
            raise ValueError("PIPELINE_PATTERN must be sequential, parallel, or hierarchical.")
        if self.max_parallel_agents < 1:
            raise ValueError("MAX_PARALLEL_AGENTS must be at least 1.")
        if self.max_hierarchy_cycles < 0:
            raise ValueError("MAX_HIERARCHY_CYCLES cannot be negative.")
        if self.event_log_verbosity not in {"quiet", "normal", "verbose"}:
            raise ValueError("EVENT_LOG_VERBOSITY must be quiet, normal, or verbose.")
