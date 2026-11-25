"""Structured HTTP request and response models."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from prd_agents.config import Provider
from prd_agents.models import (
    CoverageReport,
    RequirementPoint,
    RunReport,
    SeleniumScript,
    TestCase,
    ValidationReport,
)
from prd_agents.monitoring import MonitoringEvent


RunStatus = Literal["queued", "running", "completed", "failed"]
ProviderRole = Literal["extractor", "generator", "critic", "selenium"]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "prd-to-selenium-api"
    architecture: Literal["blackboard"] = "blackboard"
    orchestration_pattern: Literal["sequential"] = "sequential"


class SampleItem(BaseModel):
    id: str
    name: str
    filename: str


class SamplesResponse(BaseModel):
    items: list[SampleItem]


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    status: Literal["ready"] = "ready"


class RunRequest(BaseModel):
    upload_id: str | None = None
    sample_id: str | None = None

    @model_validator(mode="after")
    def require_single_source(self) -> "RunRequest":
        if (self.upload_id is None) == (self.sample_id is None):
            raise ValueError("Provide exactly one of upload_id or sample_id.")
        return self


class RunRecord(BaseModel):
    run_id: str
    filename: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    execution_time_seconds: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    architecture: Literal["blackboard"] = "blackboard"
    orchestration_pattern: Literal["sequential"] = "sequential"


class RunListResponse(BaseModel):
    items: list[RunRecord]
    total: int


class RunResultsResponse(BaseModel):
    run: RunRecord
    requirements: list[RequirementPoint]
    test_cases: list[TestCase]
    coverage: CoverageReport | None
    selenium_scripts: list[SeleniumScript]
    validation_report: ValidationReport | None
    run_report: RunReport | None


class RunEventsResponse(BaseModel):
    run_id: str
    events: list[MonitoringEvent]


class ProviderValidationRequest(BaseModel):
    role: ProviderRole


class ProviderValidationResponse(BaseModel):
    role: ProviderRole
    provider: Provider
    model: str
    configured: bool
    reachable: bool
    model_available: bool | None = None
    error_type: str | None = None
    message: str
    credential_ref_masked: str | None = None


class ModelConfigInput(BaseModel):
    provider: Provider
    model: str
    credential_ref: str | None = None


class ModelsConfigRequest(BaseModel):
    roles: dict[ProviderRole, ModelConfigInput]

    @model_validator(mode="after")
    def require_all_roles(self) -> "ModelsConfigRequest":
        required = {"extractor", "generator", "critic", "selenium"}
        if set(self.roles) != required:
            raise ValueError("Provide settings for extractor, generator, critic, and selenium.")
        return self


class ModelConfigView(BaseModel):
    provider: Provider
    model: str
    credential_configured: bool
    credential_ref_masked: str | None = None


class ModelsConfigResponse(BaseModel):
    roles: dict[ProviderRole, ModelConfigView]
