"""Persist safe model selections and resolve credentials from server-side env."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from pydantic import SecretStr

from prd_agents.config import AppConfig

from .schemas import ModelConfigInput, ModelConfigView, ProviderRole

_ROLES: tuple[ProviderRole, ...] = ("extractor", "generator", "critic", "selenium")
_PROVIDERS = {"ollama", "gemini", "groq"}
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z")


class EnvironmentCredentialResolver:
    """Resolve references without storing or returning credential values."""

    @staticmethod
    def resolve(reference: str | None) -> str | None:
        return os.getenv(reference) if reference else None

    @classmethod
    def configured(cls, reference: str | None) -> bool:
        return bool(cls.resolve(reference))


class ModelConfigStore:
    def __init__(
        self,
        db_path: Path,
        credential_resolver: type[EnvironmentCredentialResolver] = EnvironmentCredentialResolver,
    ) -> None:
        self.db_path = db_path
        self.credential_resolver = credential_resolver
        with sqlite3.connect(self.db_path, timeout=10) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_configs (
                       config_id INTEGER PRIMARY KEY CHECK (config_id = 1),
                       roles_json TEXT NOT NULL
                   )"""
            )

    @staticmethod
    def _normalize(role: str, setting: ModelConfigInput) -> ModelConfigInput:
        provider = setting.provider
        model = setting.model.strip()
        if not model or len(model) > 256 or any(ord(char) < 32 for char in model):
            raise ValueError(f"{role} model must be a non-empty model identifier.")

        prefix, separator, remainder = model.partition("/")
        if separator and prefix.lower() in _PROVIDERS:
            if prefix.lower() != provider:
                raise ValueError(
                    f"{role} model prefix '{prefix}' is incompatible with provider '{provider}'."
                )
            model = remainder
        if not model:
            raise ValueError(f"{role} model must be a non-empty model identifier.")
        if provider == "gemini" and not model.lower().startswith("gemini-"):
            raise ValueError(f"{role} Gemini models must use a gemini- model identifier.")
        if provider == "groq" and model.lower().startswith("gemini-"):
            raise ValueError(f"{role} Gemini model identifiers cannot be used with Groq.")
        if provider == "ollama" and model.lower().startswith("gemini-"):
            raise ValueError(f"{role} Gemini model identifiers cannot be used with Ollama.")

        reference = setting.credential_ref
        if reference is not None:
            if not _ENV_NAME.fullmatch(reference):
                raise ValueError(f"{role} credential_ref must be an environment variable name.")
            if provider == "ollama":
                raise ValueError(f"{role} Ollama settings must not specify a credential_ref.")
            expected_prefix = "GEMINI" if provider == "gemini" else "GROQ"
            if (
                not reference.startswith(expected_prefix)
                and reference != f"{role.upper()}_API_KEY"
            ):
                raise ValueError(
                    f"{role} {provider} credentials must reference a {expected_prefix} "
                    "or role-specific API key variable."
                )

        return ModelConfigInput(
            provider=provider,
            model=model,
            credential_ref=reference,
        )

    def get_settings(self) -> dict[ProviderRole, ModelConfigInput]:
        with sqlite3.connect(self.db_path, timeout=10) as connection:
            row = connection.execute(
                "SELECT roles_json FROM model_configs WHERE config_id = 1"
            ).fetchone()
        if row:
            stored = json.loads(row[0])
            return {
                role: self._normalize(role, ModelConfigInput.model_validate(stored[role]))
                for role in _ROLES
            }

        config = AppConfig(execution_mode="llm")
        return {
            role: self._normalize(
                role,
                ModelConfigInput(
                    provider=config.models[role].provider,
                    model=config.models[role].name,
                    credential_ref=config.models[role].credential_ref,
                ),
            )
            for role in _ROLES
        }

    def save_settings(
        self, roles: dict[ProviderRole, ModelConfigInput]
    ) -> dict[ProviderRole, ModelConfigInput]:
        existing = self.get_settings()
        normalized = {
            role: self._normalize(
                role,
                roles[role].model_copy(update={
                    "credential_ref": existing[role].credential_ref,
                })
                if (
                    "credential_ref" not in roles[role].model_fields_set
                    and roles[role].provider == existing[role].provider
                )
                else roles[role],
            )
            for role in _ROLES
        }
        safe_json = json.dumps({
            role: setting.model_dump(mode="json")
            for role, setting in normalized.items()
        })
        with sqlite3.connect(self.db_path, timeout=10) as connection:
            connection.execute(
                """INSERT INTO model_configs (config_id, roles_json) VALUES (1, ?)
                   ON CONFLICT(config_id) DO UPDATE SET roles_json = excluded.roles_json""",
                (safe_json,),
            )
        return normalized

    def app_config(self) -> AppConfig:
        config = AppConfig()
        settings = self.get_settings()
        model_settings = {}
        for role, selected in settings.items():
            previous = config.models[role]
            key = self.credential_resolver.resolve(selected.credential_ref)
            model_settings[role] = previous.model_copy(update={
                "provider": selected.provider,
                "name": selected.model,
                "api_key": SecretStr(key) if key else None,
                "credential_ref": selected.credential_ref,
            })
        return config.model_copy(update={"models": model_settings})

    def response(self) -> dict[str, ModelConfigView]:
        return {
            role: ModelConfigView(
                provider=setting.provider,
                model=setting.model,
                credential_configured=self.credential_resolver.configured(
                    setting.credential_ref
                ),
                credential_ref_masked=self._mask_reference(setting.credential_ref),
            )
            for role, setting in self.get_settings().items()
        }

    @staticmethod
    def _mask_reference(reference: str | None) -> str | None:
        if reference is None:
            return None
        if len(reference) <= 7:
            return f"{reference[:max(1, len(reference) - 1)]}****{reference[-1]}"
        return f"{reference[:4]}****{reference[-4:]}"
