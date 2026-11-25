"""Upload handling and single-process run coordination for the HTTP API."""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from prd_agents.config import AppConfig
from prd_agents.model_client import create_model_clients
from prd_agents.models import BlackboardState
from prd_agents.pipeline import run_pipeline

from .schemas import RunRecord

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
RunPipeline = Callable[..., BlackboardState]


class RunManager:
    def __init__(self, data_dir: Path, pipeline_runner: RunPipeline | None = None) -> None:
        self.data_dir = data_dir
        self.upload_dir = data_dir / "uploads"
        self.runs_dir = data_dir / "runs"
        self.db_path = data_dir / "api.sqlite3"
        self.pipeline_runner = pipeline_runner or run_pipeline
        self.model_config_provider: Callable[[], AppConfig] | None = None
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    input_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    execution_time_seconds REAL,
                    error_type TEXT,
                    error_message TEXT,
                    result_json TEXT
                );
                """
            )

    def save_upload(self, filename: str, content: bytes) -> dict[str, object]:
        safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
        suffix = Path(safe_name).suffix.lower()
        if not safe_name or suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("Upload a PRD with a .md, .txt, .pdf, or .docx extension.")
        if not content:
            raise ValueError("The uploaded PRD is empty.")
        if len(content) > MAX_UPLOAD_BYTES:
            raise OverflowError(f"PRD uploads must not exceed {MAX_UPLOAD_BYTES} bytes.")
        upload_id = str(uuid.uuid4())
        path = self.upload_dir / f"{upload_id}{suffix}"
        path.write_bytes(content)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO uploads (upload_id, filename, path, created_at) VALUES (?, ?, ?, ?)",
                (upload_id, safe_name, str(path), created_at),
            )
        return {
            "upload_id": upload_id,
            "filename": safe_name,
            "size_bytes": len(content),
        }

    @staticmethod
    def samples() -> list[dict[str, str]]:
        return [
            {"id": path.stem, "name": path.stem.replace("_", " ").title(),
             "filename": path.name}
            for path in sorted(SAMPLES_DIR.glob("*.md"))
        ]

    def create_run(self, upload_id: str | None, sample_id: str | None) -> RunRecord:
        if (upload_id is None) == (sample_id is None):
            raise ValueError("Provide exactly one of upload_id or sample_id.")
        if upload_id is not None:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT filename, path FROM uploads WHERE upload_id = ?",
                    (upload_id,),
                ).fetchone()
            if row is None:
                raise KeyError("Uploaded PRD not found.")
            filename, input_path = row["filename"], row["path"]
        else:
            sample = next((item for item in self.samples() if item["id"] == sample_id), None)
            if sample is None:
                raise KeyError("Sample PRD not found.")
            filename = sample["filename"]
            input_path = str(SAMPLES_DIR / filename)

        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO runs
                   (run_id, filename, input_path, status, created_at)
                   VALUES (?, ?, ?, 'queued', ?)""",
                (run_id, filename, input_path, created_at),
            )
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._run_record(row)

    @staticmethod
    def _run_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            filename=row["filename"],
            status=row["status"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            execution_time_seconds=row["execution_time_seconds"],
            error_type=row["error_type"],
            error_message=row["error_message"],
        )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._run_record(row) if row else None

    def list_runs(self, limit: int, offset: int) -> tuple[list[RunRecord], int]:
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._run_record(row) for row in rows], total

    def execute_run(self, run_id: str) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None or row["status"] != "queued":
                return
            started_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "UPDATE runs SET status = 'running', started_at = ? WHERE run_id = ?",
                (started_at, run_id),
            )

        started = time.monotonic()
        run_dir = self.runs_dir / run_id
        try:
            base_config = (
                self.model_config_provider()
                if self.model_config_provider is not None else AppConfig()
            )
            config = base_config.model_copy(update={
                "arch": "blackboard",
                "pipeline": "sequential_loop",
                "pipeline_pattern": "sequential",
            })
            config.validate_runtime()
            state = self.pipeline_runner(
                Path(row["input_path"]), run_dir, config, create_model_clients(config),
                run_id=run_id,
            )
            result = {
                "requirements": [item.model_dump(mode="json") for item in state.requirement_points],
                "test_cases": [item.model_dump(mode="json") for item in state.test_cases],
                "coverage": state.coverage.model_dump(mode="json") if state.coverage else None,
                "selenium_scripts": [
                    item.model_dump(mode="json") for item in state.selenium_scripts
                ],
                "validation_report": (
                    state.validation_report.model_dump(mode="json")
                    if state.validation_report else None
                ),
                "run_report": state.run_report.model_dump(mode="json") if state.run_report else None,
            }
            self._finish_run(run_id, "completed", time.monotonic() - started,
                             result_json=json.dumps(result))
        except Exception as exc:
            logger.exception("Pipeline run %s failed", run_id)
            self._finish_run(
                run_id, "failed", time.monotonic() - started,
                error_type=type(exc).__name__,
                error_message="Pipeline execution failed. Check backend logs for details.",
            )

    def _finish_run(self, run_id: str, status: str, duration: float,
                    result_json: str | None = None, error_type: str | None = None,
                    error_message: str | None = None) -> None:
        completed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """UPDATE runs SET status = ?, completed_at = ?,
                   execution_time_seconds = ?, error_type = ?, error_message = ?,
                   result_json = ? WHERE run_id = ?""",
                (status, completed_at, duration, error_type, error_message,
                 result_json, run_id),
            )

    def get_results(self, run_id: str) -> tuple[RunRecord | None, dict | None]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None, None
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return self._run_record(row), result

    def get_events(self, run_id: str) -> tuple[RunRecord | None, list[dict]]:
        record = self.get_run(run_id)
        if record is None:
            return None, []
        from prd_agents.config import AppConfig
        event_path = (
            self.runs_dir / run_id / AppConfig().monitoring_dir / "events.jsonl"
        )
        if not event_path.exists():
            return record, []
        events = []
        for line in event_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return record, events
