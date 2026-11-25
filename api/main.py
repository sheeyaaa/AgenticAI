
"""FastAPI endpoints for uploading PRDs and running the sequential pipeline."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware

from prd_agents.model_client import create_model_clients

from .model_settings import ModelConfigStore
from .run_manager import MAX_UPLOAD_BYTES, RunManager
from .schemas import (
    HealthResponse,
    ModelsConfigRequest,
    ModelsConfigResponse,
    RunEventsResponse,
    RunListResponse,
    RunRecord,
    RunRequest,
    RunResultsResponse,
    SamplesResponse,
    UploadResponse,
    ProviderValidationRequest,
    ProviderValidationResponse,
)

logger = logging.getLogger(__name__)


def get_cors_origins(
    cors_origins: list[str] | None = None,
) -> list[str]:
    """
    Load and normalize allowed frontend origins.

    Explicit function arguments take priority over environment variables.
    """

    if cors_origins is not None:
        origins = cors_origins

    else:
        env_origins = os.getenv("CORS_ORIGINS")

        if env_origins:
            origins = env_origins.split(",")

        else:
            origins = [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "https://agentic-kj7805vfe-sheeyaaa.vercel.app",
            ]

    normalized_origins = [
        origin.strip().rstrip("/")
        for origin in origins
        if origin and origin.strip()
    ]

    if not normalized_origins:
        raise RuntimeError(
            "No CORS origins configured. "
            "Set CORS_ORIGINS in the environment."
        )

    logger.info(
        "Configured CORS allowed origins: %s",
        normalized_origins,
    )

    return normalized_origins


def create_app(
    data_dir: Path | None = None,
    pipeline_runner=None,
    cors_origins: list[str] | None = None,
) -> FastAPI:

    app = FastAPI(
        title="PRD-to-Selenium API",
        version="1.0.0",
    )

    # --------------------------------------------------
    # CORS CONFIGURATION
    # --------------------------------------------------

    configured_origins = get_cors_origins(cors_origins)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info(
        "CORS middleware initialized successfully."
    )

    # --------------------------------------------------
    # STORAGE AND APPLICATION INITIALIZATION
    # --------------------------------------------------

    default_data_dir = (
        Path(tempfile.gettempdir())
        / "prd-to-selenium-api"
    )

    storage_dir = data_dir or Path(
        os.getenv(
            "API_DATA_DIR",
            str(default_data_dir),
        )
    )

    app.state.run_manager = RunManager(
        storage_dir,
        pipeline_runner,
    )

    app.state.model_config_store = ModelConfigStore(
        app.state.run_manager.db_path
    )

    app.state.run_manager.model_config_provider = (
        app.state.model_config_store.app_config
    )

    # --------------------------------------------------
    # HEALTH CHECK
    # --------------------------------------------------

    @app.get(
        "/health",
        response_model=HealthResponse,
    )
    def health() -> HealthResponse:
        return HealthResponse()

    # --------------------------------------------------
    # SAMPLE PRDS
    # --------------------------------------------------

    @app.get(
        "/api/samples",
        response_model=SamplesResponse,
    )
    def samples() -> SamplesResponse:
        return SamplesResponse(
            items=app.state.run_manager.samples()
        )

    # --------------------------------------------------
    # UPLOAD PRD
    # --------------------------------------------------

    @app.post(
        "/api/upload-prd",
        response_model=UploadResponse,
        status_code=201,
    )
    async def upload_prd(
        file: UploadFile = File(...),
    ) -> UploadResponse:

        try:
            content = await file.read(
                MAX_UPLOAD_BYTES + 1
            )

            data = app.state.run_manager.save_upload(
                file.filename or "",
                content,
            )

            return UploadResponse.model_validate(data)

        except OverflowError as exc:
            raise HTTPException(
                status_code=413,
                detail=str(exc),
            ) from exc

        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        finally:
            await file.close()

    # --------------------------------------------------
    # START PRD PIPELINE
    # --------------------------------------------------

    @app.post(
        "/api/run",
        response_model=RunRecord,
        status_code=202,
    )
    def run_prd(
        request: RunRequest,
        background_tasks: BackgroundTasks,
    ) -> RunRecord:

        try:
            run = app.state.run_manager.create_run(
                request.upload_id,
                request.sample_id,
            )

        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail=str(exc).strip("'"),
            ) from exc

        background_tasks.add_task(
            app.state.run_manager.execute_run,
            run.run_id,
        )

        return run

    # --------------------------------------------------
    # LIST PIPELINE RUNS
    # --------------------------------------------------

    @app.get(
        "/api/runs",
        response_model=RunListResponse,
    )
    def list_runs(
        limit: int = Query(
            default=50,
            ge=1,
            le=100,
        ),
        offset: int = Query(
            default=0,
            ge=0,
        ),
    ) -> RunListResponse:

        items, total = app.state.run_manager.list_runs(
            limit,
            offset,
        )

        return RunListResponse(
            items=items,
            total=total,
        )

    # --------------------------------------------------
    # GET INDIVIDUAL RUN
    # --------------------------------------------------

    @app.get(
        "/api/runs/{run_id}",
        response_model=RunRecord,
    )
    def get_run(run_id: str) -> RunRecord:

        run = app.state.run_manager.get_run(run_id)

        if run is None:
            raise HTTPException(
                status_code=404,
                detail="Run not found.",
            )

        return run

    # --------------------------------------------------
    # GET RUN RESULTS
    # --------------------------------------------------

    @app.get(
        "/api/runs/{run_id}/results",
        response_model=RunResultsResponse,
    )
    def get_results(
        run_id: str,
    ) -> RunResultsResponse:

        run, result = app.state.run_manager.get_results(
            run_id
        )

        if run is None:
            raise HTTPException(
                status_code=404,
                detail="Run not found.",
            )

        if run.status in {"queued", "running"}:
            raise HTTPException(
                status_code=409,
                detail="Run results are not ready.",
            )

        if run.status == "failed" or result is None:
            raise HTTPException(
                status_code=409,
                detail="Run did not produce results.",
            )

        return RunResultsResponse(
            run=run,
            **result,
        )

    # --------------------------------------------------
    # GET RUN EVENTS
    # --------------------------------------------------

    @app.get(
        "/api/runs/{run_id}/events",
        response_model=RunEventsResponse,
    )
    def get_events(
        run_id: str,
    ) -> RunEventsResponse:

        run, events = app.state.run_manager.get_events(
            run_id
        )

        if run is None:
            raise HTTPException(
                status_code=404,
                detail="Run not found.",
            )

        return RunEventsResponse(
            run_id=run_id,
            events=events,
        )

    # --------------------------------------------------
    # GET MODEL CONFIGURATION
    # --------------------------------------------------

    @app.get(
        "/api/models/config",
        response_model=ModelsConfigResponse,
    )
    def get_model_config() -> ModelsConfigResponse:

        return ModelsConfigResponse(
            roles=app.state.model_config_store.response()
        )

    # --------------------------------------------------
    # UPDATE MODEL CONFIGURATION
    # --------------------------------------------------

    @app.put(
        "/api/models/config",
        response_model=ModelsConfigResponse,
    )
    def put_model_config(
        request: ModelsConfigRequest,
    ) -> ModelsConfigResponse:

        try:
            app.state.model_config_store.save_settings(
                request.roles
            )

        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        return ModelsConfigResponse(
            roles=app.state.model_config_store.response()
        )

    # --------------------------------------------------
    # MODEL CONNECTION VALIDATION
    # --------------------------------------------------

    def test_role_model(
        role: str,
    ) -> ProviderValidationResponse:

        config = (
            app.state.model_config_store
            .app_config()
            .model_copy(
                update={"execution_mode": "llm"}
            )
        )

        setting = config.models[role]

        check = create_model_clients(
            config
        )[role].validate_connection()

        role_view = (
            app.state.model_config_store.response()[role]
        )

        return ProviderValidationResponse(
            role=role,
            provider=setting.provider,
            model=setting.name,
            credential_ref_masked=(
                role_view.credential_ref_masked
            ),
            **check,
        )

    @app.post(
        "/api/models/test",
        response_model=ProviderValidationResponse,
    )
    def test_model(
        request: ProviderValidationRequest,
    ) -> ProviderValidationResponse:

        return test_role_model(request.role)

    @app.post(
        "/api/providers/validate",
        response_model=ProviderValidationResponse,
    )
    def validate_provider(
        request: ProviderValidationRequest,
    ) -> ProviderValidationResponse:

        return test_role_model(request.role)

    return app


app = create_app()
