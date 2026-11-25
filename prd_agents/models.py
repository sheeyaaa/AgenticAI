"""Pydantic contracts shared by every agent and service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DocumentSection(BaseModel):
    heading: str
    content: str
    level: int = 1
    source_location: str = ""


class Document(BaseModel):
    source_path: str
    title: str
    sections: list[DocumentSection] = Field(default_factory=list)
    text: str


class Chunk(BaseModel):
    id: str
    text: str
    section_heading: str = ""


class RequirementPoint(BaseModel):
    id: str
    text: str
    source_chunk_id: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    source_section: str = ""


class RequirementPoints(BaseModel):
    items: list[RequirementPoint] = Field(default_factory=list)


TestType = Literal["positive", "negative", "edge"]


class Locator(BaseModel):
    strategy: Literal["id", "css selector", "xpath", "name", "tag name", "link text"]
    value: str


class BrowserAction(BaseModel):
    action: Literal[
        "navigate", "click", "fill", "select", "assert_text",
        "assert_visible", "assert_url", "assert_element_count",
    ]
    value: str = ""
    locator: Locator | None = None
    expected: str = ""


class TestCase(BaseModel):
    id: str
    req_ids: list[str]
    title: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    expected_result: str
    type: TestType
    priority: Literal["high", "medium", "low"] = "medium"
    actions: list[BrowserAction] = Field(default_factory=list)


class TestCases(BaseModel):
    items: list[TestCase] = Field(default_factory=list)


class Chunks(BaseModel):
    items: list[Chunk] = Field(default_factory=list)


class CoverageReport(BaseModel):
    covered_requirement_ids: list[str] = Field(default_factory=list)
    uncovered_requirement_ids: list[str] = Field(default_factory=list)
    missing_positive_requirement_ids: list[str] = Field(default_factory=list)
    missing_negative_requirement_ids: list[str] = Field(default_factory=list)
    missing_edge_requirement_ids: list[str] = Field(default_factory=list)
    invalid_requirement_ids: list[str] = Field(default_factory=list)
    behaviorally_verified_requirement_ids: list[str] = Field(default_factory=list)
    score: float = Field(ge=0, le=1)


class Critique(BaseModel):
    score: float = Field(ge=0, le=1)
    coverage_score: float = Field(ge=0, le=1)
    missing_req_ids: list[str] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)


class IterationRecord(BaseModel):
    iteration: int
    score: float
    coverage_score: float
    test_cases: list[TestCase]
    critique: Critique


class SeleniumScript(BaseModel):
    test_case_id: str
    filename: str
    code: str
    locators: list[Locator] = Field(default_factory=list)


class ValidationReport(BaseModel):
    valid: bool
    script_results: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    validated_count: int = 0
    rejected_count: int = 0


class RunReport(BaseModel):
    run_id: str | None = None
    source_path: str
    iterations: int
    final_quality_score: float
    final_coverage_score: float
    deterministic_coverage_percent: float
    remaining_gaps: dict[str, list[str]]
    requirement_count: int
    test_case_count: int
    script_count: int = 0
    elapsed_seconds: float
    estimated_token_counts: dict[str, int]
    provider_usage: dict[str, dict[str, object]] = Field(default_factory=dict)
    estimated_api_cost_usd: float | None = None
    scripts_validated: int = 0
    scripts_rejected: int = 0
    tests_executed: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_blocked: int | None = None
    execution_mode: str = "deterministic"
    architecture: str = "blackboard"
    orchestration_pattern: str = "sequential"
    effective_config: dict[str, object] = Field(default_factory=dict)
    models_used: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[str] = Field(default_factory=list)


class WriteLogEntry(BaseModel):
    agent: str
    key: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int


class BlackboardState(BaseModel):
    """Versioned state contract. All writes are validated through Blackboard."""
    model_config = ConfigDict(validate_assignment=True)
    document: Document | None = None
    chunks: list[Chunk] = Field(default_factory=list)
    requirement_points: list[RequirementPoint] = Field(default_factory=list)
    test_cases: list[TestCase] = Field(default_factory=list)
    coverage: CoverageReport | None = None
    critique: Critique | None = None
    history: list[IterationRecord] = Field(default_factory=list)
    stale_iterations: int = 0
    iteration: int = 0
    token_stats: dict[str, int] = Field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    selenium_scripts: list[SeleniumScript] = Field(default_factory=list)
    validation_report: ValidationReport | None = None
    run_report: RunReport | None = None
    write_log: list[WriteLogEntry] = Field(default_factory=list)
