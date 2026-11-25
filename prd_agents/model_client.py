"""Provider-aware, server-side LLM clients with bounded retries and usage accounting."""
from __future__ import annotations
from pyexpat import model
import litellm
import json
import time
import urllib.error
import urllib.request
from typing import Any

from pydantic import SecretStr

from .config import AppConfig, ModelSetting, Provider
from .pipeline import ModelClient


class ProviderCallError(RuntimeError):
    def __init__(self, provider: str, kind: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.retryable = retryable


def _secret_value(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


class ProviderModelClient:
    def __init__(self, setting: ModelSetting, base_url: str, timeout: float = 300,
                 max_retries: int = 2, retry_base_seconds: float = 1,
                 retry_max_seconds: float = 8, role: str = "model") -> None:
        self.setting = setting
        self.provider = setting.provider
        self.model = setting.name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.role = role
        self.calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._usage_complete = True
        self._estimated_cost = 0.0
        self._cost_complete = True
        self.fallback_used = False
        self.last_provider = self.provider
        self.last_model = self.model

    def complete(self, prompt: str) -> str:
        if self.timeout <= 0 or self.max_retries < 0:
            raise ValueError("Model timeout must be positive and retry count non-negative.")
        try:
            return self._complete_with(
                self.provider, self.model, self.setting.api_key,
                self.setting.input_cost_per_million_tokens,
                self.setting.output_cost_per_million_tokens, prompt,
            )
        except ProviderCallError:
            if not self.setting.fallback_model:
                raise
        self.fallback_used = True
        fallback_provider = self.setting.fallback_provider or self.provider
        fallback_key = self.setting.fallback_api_key
        if fallback_key is None and fallback_provider == self.provider:
            fallback_key = self.setting.api_key
        try:
            return self._complete_with(
                fallback_provider,
                self.setting.fallback_model,
                fallback_key,
                self.setting.fallback_input_cost_per_million_tokens,
                self.setting.fallback_output_cost_per_million_tokens,
                prompt,
            )
        except ProviderCallError:
            raise ProviderCallError(
                self.provider, "fallback_failed",
                "Both the configured model and fallback model failed.",
            ) from None

    def _complete_with(self, provider: Provider, model: str,
                       api_key: SecretStr | None, input_price: float | None,
                       output_price: float | None, prompt: str) -> str:
        key = _secret_value(api_key)
        if provider != "ollama" and not key:
            raise ProviderCallError(
                provider, "configuration",
                f"No server-side API key is configured for the {self.role} {provider} provider.",
            )
        for attempt in range(self.max_retries + 1):
            try:
                response = self._invoke(provider, model, key, prompt)
                content = self._response_content(response)
                if not content.strip():
                    raise ProviderCallError(
                        provider, "empty_response", "The model provider returned an empty response."
                    )
                self._record_usage(response, input_price, output_price)
                self.last_provider = provider
                self.last_model = model
                return content
            except ProviderCallError as exc:
                error = exc
            except Exception as exc:
                error = self._provider_error(provider, exc)
            if not error.retryable or attempt >= self.max_retries:
                raise error from None
            delay = min(
                self.retry_base_seconds * (2 ** attempt),
                self.retry_max_seconds,
            )
            time.sleep(delay)
        raise ProviderCallError(provider, "unknown", "The model request failed.")

    def _invoke(
        self,
        provider: Provider,
        model: str,
        api_key: str | None,
        prompt: str
    ) -> Any:

        request: dict[str, Any] = {
            "model": f"{provider}/{model}",
            "messages": [{"role": "user", "content": prompt}],
            "timeout": self.timeout,
            "num_retries": 0,
    }

        if provider == "ollama":
            request["api_base"] = self.base_url
        elif api_key:
            request["api_key"] = api_key

        return litellm.completion(**request)

    @staticmethod
    def _response_content(response: Any) -> str:
        if isinstance(response, dict):
            choices = response.get("choices") or []
            message = choices[0].get("message", {}) if choices else {}
            content = message.get("content", "")
        else:
            choices = getattr(response, "choices", []) or []
            message = getattr(choices[0], "message", None) if choices else None
            content = getattr(message, "content", "") if message is not None else ""
        if isinstance(content, list):
            content = "".join(
                item.get("text", "") if isinstance(item, dict)
                else str(getattr(item, "text", ""))
                for item in content
            )
        return content if isinstance(content, str) else ""

    def _record_usage(self, response: Any, input_price: float | None,
                      output_price: float | None) -> None:
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        if usage is None:
            self._usage_complete = False
            self._cost_complete = False
            self.calls += 1
            return
        input_tokens = self._usage_value(usage, "prompt_tokens", "input_tokens")
        output_tokens = self._usage_value(usage, "completion_tokens", "output_tokens")
        if input_tokens is None or output_tokens is None:
            self._usage_complete = False
            self._cost_complete = False
        else:
            self._input_tokens += input_tokens
            self._output_tokens += output_tokens
            if input_price is None or output_price is None:
                self._cost_complete = False
            else:
                self._estimated_cost += (
                    input_tokens * input_price + output_tokens * output_price
                ) / 1_000_000
        self.calls += 1

    @staticmethod
    def _usage_value(usage: Any, *names: str) -> int | None:
        for name in names:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if isinstance(value, (int, float)):
                return int(value)
        return None

    @staticmethod
    def _provider_error(provider: str, exc: Exception) -> ProviderCallError:
        name = type(exc).__name__.lower()
        status = getattr(exc, "status_code", getattr(exc, "code", None))
        try:
            status = int(status) if status is not None else None
        except (TypeError, ValueError):
            status = None
        if status == 429 or "ratelimit" in name:
            return ProviderCallError(provider, "rate_limit", "Provider rate limit exceeded.", True)
        if status in {401, 403} or "authentication" in name or "permission" in name:
            return ProviderCallError(provider, "authentication", "Provider authentication failed.")
        if isinstance(exc, (TimeoutError,)) or "timeout" in name:
            return ProviderCallError(provider, "timeout", "Provider request timed out.", True)
        if status is not None and status >= 500 or "serviceunavailable" in name:
            return ProviderCallError(provider, "service_unavailable",
                                     "Provider service is temporarily unavailable.", True)
        if "connection" in name or isinstance(exc, urllib.error.URLError):
            return ProviderCallError(provider, "connection", "Could not connect to the provider.", True)
        if status == 400 or "badrequest" in name:
            return ProviderCallError(provider, "bad_request", "Provider rejected the model request.")
        return ProviderCallError(provider, "provider_error", "The provider request failed.")

    def validate_connection(self) -> dict[str, Any]:
        api_key = _secret_value(self.setting.api_key)
        if self.provider != "ollama" and not api_key:
            return {
                "configured": False,
                "reachable": False,
                "model_available": None,
                "error_type": "configuration",
                "message": f"No server-side API key is configured for {self.role}.",
            }
        if self.provider == "ollama":
            url = f"{self.base_url}/api/tags"
            headers: dict[str, str] = {}
        elif self.provider == "groq":
            url = "https://api.groq.com/openai/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            headers = {"x-goog-api-key": api_key or ""}
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)
            model_available = self._model_is_available(payload, self.model)
            return {
                "configured": True,
                "reachable": True,
                "model_available": model_available,
                "error_type": None if model_available else "model_unavailable",
                "message": "Provider and configured model are available."
                if model_available else "Provider is reachable, but the configured model was not listed.",
            }
        except Exception as exc:
            error = self._provider_error(self.provider, exc)
            return {
                "configured": True,
                "reachable": False,
                "model_available": None,
                "error_type": error.kind,
                "message": str(error),
            }

    @staticmethod
    def _model_is_available(payload: Any, model: str) -> bool:
        if not isinstance(payload, dict):
            return False
        items = payload.get("data") or payload.get("models") or []
        names = {
            str(item.get("id") or item.get("name") or "").removeprefix("models/")
            for item in items if isinstance(item, dict)
        }
        return model in names

    @property
    def usage_summary(self) -> dict[str, Any]:
        return {
            "provider": self.last_provider,
            "model": self.last_model,
            "calls": self.calls,
            "input_tokens": self._input_tokens if self.calls and self._usage_complete else None,
            "output_tokens": self._output_tokens if self.calls and self._usage_complete else None,
            "usage_available": bool(self.calls and self._usage_complete),
            "estimated_cost_usd": (
                self._estimated_cost if self.calls and self._usage_complete and self._cost_complete
                else None
            ),
            "fallback_used": self.fallback_used,
        }


class OllamaClient(ProviderModelClient):
    """Compatibility wrapper retained for existing benchmark callers."""

    def __init__(self, model: str, base_url: str, timeout: float = 300) -> None:
        clean_model = model.removeprefix("ollama/")
        super().__init__(
            ModelSetting(provider="ollama", name=clean_model),
            base_url=base_url,
            timeout=timeout,
            max_retries=2,
            role="model",
        )


def create_model_clients(config: AppConfig) -> dict[str, ModelClient]:
    if config.execution_mode != "llm":
        return {}
    return {
        role: ProviderModelClient(
            setting=setting,
            base_url=config.ollama_base_url,
            timeout=config.model_timeout_seconds,
            max_retries=config.model_max_retries,
            retry_base_seconds=config.model_retry_base_seconds,
            retry_max_seconds=config.model_retry_max_seconds,
            role=role,
        )
        for role, setting in config.models.items()
    }
