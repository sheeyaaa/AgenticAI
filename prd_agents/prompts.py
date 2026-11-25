"""Prompt variants used to reduce dependence on one prompt shape."""
from __future__ import annotations

from typing import Final


_VARIANTS: Final[dict[str, tuple[str, ...]]] = {
    "extractor": (
        "Extract requirement points as a JSON array. Each item must contain "
        "id, text, source_chunk_id, source_section, and acceptance_criteria.",
        "Identify independently testable requirements and return only a JSON "
        "array with id, text, source_chunk_id, source_section, and acceptance_criteria.",
    ),
    "generator": (
        "Generate test cases as a JSON array. Each object must use these exact fields: "
        "id, req_ids, title, preconditions, steps, expected_result, type, priority, actions. "
        "req_ids must be an array of input requirement IDs; preconditions and steps must be "
        "arrays of strings. actions must be an array of objects with action, value, locator, "
        "and expected fields, or an empty array when UI details are unknown. type must be "
        "positive, negative, or edge; priority must be high, medium, or low. Return only JSON, "
        "without Markdown fences:",
        "Design positive, negative, and edge test cases as a JSON array. Each object must use "
        "these exact fields: id, req_ids, title, preconditions, steps, expected_result, type, "
        "priority, actions. req_ids must be an array of input requirement IDs; preconditions "
        "and steps must be arrays of strings. actions must be an array of objects with action, "
        "value, locator, and expected fields, or an empty array when UI details are unknown. "
        "type must be positive, negative, or edge; priority must be high, medium, or low. "
        "Return only JSON, without Markdown fences:",
    ),
    "critic": (
        "Critique this test suite. Return a JSON object with numeric score and coverage_score "
        "between 0 and 1, missing_req_ids as an array of requirement ID strings, and feedback "
        "as an array of strings:",
        "Review this suite for quality and traceability. Emit only a JSON object with numeric "
        "score and coverage_score between 0 and 1, missing_req_ids as an array of requirement "
        "ID strings, and feedback as an array of strings:",
    ),
}


def prompt_prefix(role: str, variant: int) -> str:
    """Return a stable prompt variant selected by deterministic input shape."""
    choices = _VARIANTS[role]
    return choices[variant % len(choices)]
