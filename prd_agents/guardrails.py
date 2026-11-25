"""Deterministic input and structured-output guardrails."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .models import Document


GuardrailCategory = Literal["prompt_injection", "abusive_language"]


class GuardrailFinding(BaseModel):
    category: GuardrailCategory
    line: int = Field(ge=1)
    reason: str


class GuardrailReport(BaseModel):
    allowed: bool
    findings: list[GuardrailFinding] = Field(default_factory=list)


class GuardrailViolation(ValueError):
    """Raised when an input PRD is unsafe to send to agents or tools."""

    def __init__(self, report: GuardrailReport) -> None:
        self.report = report
        details = "; ".join(
            f"{item.category} on line {item.line}: {item.reason}"
            for item in report.findings
        )
        super().__init__(f"PRD rejected by guardrails. {details}")


_INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bignore\s+(all\s+)?previous\s+instructions\b", "instruction override"),
    (r"\b(system|developer)\s+prompt\b", "prompt extraction or impersonation"),
    (r"\breveal\s+(the\s+)?(secret|hidden|system)\b", "secret disclosure request"),
    (r"\bbypass\s+(safety|security|guardrails)\b", "guardrail bypass request"),
    (r"\b(jailbreak|prompt injection)\b", "explicit attack language"),
    (r"\bexecute\s+(the\s+following\s+)?commands?\b", "command execution request"),
    (r"\btreat\s+the\s+following\s+as\s+instructions\b", "embedded instruction request"),
)
_ABUSE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(fuck|fucking|shit|bullshit)\b", "profanity"),
    (r"\b(idiot|stupid|moron|dumbass)\b", "insult"),
    (r"\bkill\s+yourself\b", "threatening or self-harm language"),
)


def validate_document(document: Document) -> GuardrailReport:
    """Scan every source line before chunking or model/tool calls."""
    findings: list[GuardrailFinding] = []
    for line_number, line in enumerate(document.text.splitlines(), start=1):
        for pattern, reason in _INJECTION_PATTERNS:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append(
                    GuardrailFinding(
                        category="prompt_injection", line=line_number, reason=reason
                    )
                )
        for pattern, reason in _ABUSE_PATTERNS:
            if re.search(pattern, line, flags=re.IGNORECASE):
                findings.append(
                    GuardrailFinding(
                        category="abusive_language", line=line_number, reason=reason
                    )
                )
    return GuardrailReport(allowed=not findings, findings=findings)


def validate_tool_result(value: object, model: type[BaseModel]) -> BaseModel:
    """Validate an MCP/tool result before it enters agent state."""
    if isinstance(value, BaseModel):
        return model.model_validate(value.model_dump())
    if isinstance(value, dict):
        return model.model_validate(value)
    raise TypeError(f"Tool result must be an object or mapping, got {type(value).__name__}.")
