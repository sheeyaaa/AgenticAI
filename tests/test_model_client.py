import io
from types import SimpleNamespace

import litellm
import pytest
from pydantic import SecretStr

from prd_agents.config import AppConfig, ModelSetting
from prd_agents.model_client import ProviderModelClient, create_model_clients


def test_agent_roles_use_independent_server_side_provider_settings(monkeypatch) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "llm")
    monkeypatch.setenv("EXTRACTOR_PROVIDER", "ollama")
    monkeypatch.setenv("GENERATOR_PROVIDER", "groq")
    monkeypatch.setenv("GENERATOR_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GENERATOR_API_KEY", "generator-secret")
    monkeypatch.setenv("CRITIC_PROVIDER", "gemini")
    monkeypatch.setenv("CRITIC_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("CRITIC_API_KEY", "critic-secret")
    monkeypatch.setenv("SELENIUM_PROVIDER", "groq")
    monkeypatch.setenv("SELENIUM_MODEL", "llama-3.1-8b-instant")
    monkeypatch.setenv("SELENIUM_API_KEY", "selenium-secret")
    for name in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    config = AppConfig(execution_mode="llm")
    clients = create_model_clients(config)

    assert config.models["generator"].provider == "groq"
    assert config.models["critic"].provider == "gemini"
    assert clients["generator"].model == "llama-3.3-70b-versatile"
    assert clients["critic"].model == "gemini-2.5-flash"
    assert config.models["generator"].api_key.get_secret_value() == "generator-secret"
    assert config.models["critic"].api_key.get_secret_value() == "critic-secret"
    assert "generator-secret" not in repr(config)
    assert "critic-secret" not in str(config.model_dump(mode="json"))


def test_agent_roles_can_reference_distinct_environment_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "llm")
    monkeypatch.setenv("GENERATOR_PROVIDER", "gemini")
    monkeypatch.setenv("GENERATOR_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GENERATOR_API_KEY_REF", "GEMINI_API_KEY2")
    monkeypatch.setenv("CRITIC_PROVIDER", "gemini")
    monkeypatch.setenv("CRITIC_MODEL", "gemini-2.5-pro")
    monkeypatch.setenv("CRITIC_API_KEY_REF", "GEMINI_API_KEY3")
    monkeypatch.setenv("GEMINI_API_KEY2", "generator-secret")
    monkeypatch.setenv("GEMINI_API_KEY3", "critic-secret")
    for name in (
        "GENERATOR_API_KEY", "CRITIC_API_KEY", "GEMINI_API_KEY",
        "GEMINI_API_KEY2", "GEMINI_API_KEY3",
    ):
        if name not in {"GEMINI_API_KEY2", "GEMINI_API_KEY3"}:
            monkeypatch.delenv(name, raising=False)

    config = AppConfig(execution_mode="llm")

    assert config.models["generator"].credential_ref == "GEMINI_API_KEY2"
    assert config.models["critic"].credential_ref == "GEMINI_API_KEY3"
    assert config.models["generator"].name != config.models["critic"].name
    assert config.models["generator"].api_key.get_secret_value() == "generator-secret"
    assert config.models["critic"].api_key.get_secret_value() == "critic-secret"


def test_groq_litellm_completion_tracks_usage_and_cost(monkeypatch) -> None:
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"valid":true}'))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500),
        )

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = ProviderModelClient(
        ModelSetting(
            provider="groq", name="llama-3.3-70b-versatile",
            api_key=SecretStr("private-key"),
            input_cost_per_million_tokens=0.5,
            output_cost_per_million_tokens=1.0,
        ),
        base_url="http://localhost:11434",
    )

    assert client.complete("short prompt") == '{"valid":true}'
    assert calls[0]["model"] == "groq/llama-3.3-70b-versatile"
    assert calls[0]["api_key"] == "private-key"
    assert calls[0]["timeout"] == 300
    assert client.usage_summary["input_tokens"] == 1000
    assert client.usage_summary["output_tokens"] == 500
    assert client.usage_summary["estimated_cost_usd"] == pytest.approx(0.001)
    assert "private-key" not in repr(client.usage_summary)


def test_gemini_uses_its_provider_model_and_api_key(monkeypatch) -> None:
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return {
            "choices": [{"message": {"content": "gemini response"}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 5},
        }

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = ProviderModelClient(
        ModelSetting(provider="gemini", name="gemini-2.5-flash",
                     api_key=SecretStr("gemini-server-key")),
        base_url="http://localhost:11434",
    )

    assert client.complete("prompt") == "gemini response"
    assert calls[0]["model"] == "gemini/gemini-2.5-flash"
    assert calls[0]["api_key"] == "gemini-server-key"


def test_rate_limit_retries_with_exponential_backoff(monkeypatch) -> None:
    class RateLimitError(Exception):
        status_code = 429

    attempts = []
    delays = []

    def fake_completion(**kwargs):
        attempts.append(kwargs)
        if len(attempts) == 1:
            raise RateLimitError()
        return {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3},
        }

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr("prd_agents.model_client.time.sleep", delays.append)
    client = ProviderModelClient(
        ModelSetting(provider="gemini", name="gemini-2.5-flash",
                     api_key=SecretStr("test-key")),
        base_url="http://localhost:11434",
        max_retries=2,
        retry_base_seconds=0.25,
    )

    assert client.complete("prompt") == "ok"
    assert len(attempts) == 2
    assert delays == [0.25]


def test_optional_fallback_model_is_used_after_primary_failure(monkeypatch) -> None:
    models = []

    def fake_completion(**kwargs):
        models.append(kwargs["model"])
        if len(models) == 1:
            raise ConnectionError()
        return {
            "choices": [{"message": {"content": "fallback response"}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = ProviderModelClient(
        ModelSetting(
            provider="groq", name="primary",
            api_key=SecretStr("primary-key"),
            fallback_provider="gemini", fallback_model="backup",
            fallback_api_key=SecretStr("backup-key"),
        ),
        base_url="http://localhost:11434",
        max_retries=0,
    )

    assert client.complete("prompt") == "fallback response"
    assert models == ["groq/primary", "gemini/backup"]
    assert client.usage_summary["fallback_used"] is True
    assert client.usage_summary["provider"] == "gemini"


def test_provider_connection_check_uses_server_credentials(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return io.BytesIO(b'{"data":[{"id":"llama-cloud"}]}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = ProviderModelClient(
        ModelSetting(provider="groq", name="llama-cloud",
                     api_key=SecretStr("server-only-key")),
        base_url="http://localhost:11434",
        timeout=17,
    )

    result = client.validate_connection()
    assert result["configured"] is True
    assert result["reachable"] is True
    assert result["model_available"] is True
    assert captured["timeout"] == 17
    assert captured["request"].get_header("Authorization") == "Bearer server-only-key"
    assert "server-only-key" not in str(result)


def test_missing_provider_key_does_not_make_a_network_request(monkeypatch) -> None:
    def unexpected_request(*args, **kwargs):
        raise AssertionError("No API request should be made without a key.")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_request)
    result = ProviderModelClient(
        ModelSetting(provider="gemini", name="gemini-2.5-flash"),
        base_url="http://localhost:11434",
    ).validate_connection()
    assert result["configured"] is False
    assert result["reachable"] is False


def test_fallback_provider_never_receives_the_primary_providers_key(monkeypatch) -> None:
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ConnectionError()
        return {
            "choices": [{"message": {"content": "fallback"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }

    monkeypatch.setattr(litellm, "completion", fake_completion)
    client = ProviderModelClient(
        ModelSetting(
            provider="groq", name="primary",
            api_key=SecretStr("groq-only-key"),
            fallback_provider="gemini", fallback_model="backup",
        ),
        base_url="http://localhost:11434",
        max_retries=0,
    )

    with pytest.raises(Exception, match="fallback model failed"):
        client.complete("prompt")
    assert calls[0]["api_key"] == "groq-only-key"
    assert len(calls) == 1
