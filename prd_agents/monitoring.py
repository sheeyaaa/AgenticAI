"""Typed, safe monitoring events and run visualizations."""
from __future__ import annotations

import csv
import json
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field


class MonitoringEvent(BaseModel):
    run_id: str
    trace_id: str
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_name: str = ""
    orchestration_pattern: str = ""
    event_type: str
    status: str
    duration_ms: float | None = None
    parent_agent: str = ""
    parent_task_id: str = ""
    input_summary: str = ""
    output_summary: str = ""
    error_type: str = ""
    error_message: str = ""
    retry_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


Callback = Callable[[MonitoringEvent], None]


class Monitor:
    def __init__(self, output_dir: Path, pattern: str, enabled: bool = True,
                 verbosity: str = "normal", run_id: str | None = None,
                 directory_name: str = "monitoring") -> None:
        self.output_dir = output_dir
        self.pattern = pattern
        self.enabled = enabled
        self.verbosity = verbosity
        self.run_id = run_id or str(uuid.uuid4())
        self.directory_name = directory_name
        self.trace_id = str(uuid.uuid4())
        self.events: list[MonitoringEvent] = []
        self.callbacks: list[Callback] = []
        self._starts: dict[str, list[float]] = defaultdict(list)

    def register(self, callback: Callback) -> None:
        self.callbacks.append(callback)

    def emit(self, event_type: str, status: str, agent_name: str = "",
             **kwargs: Any) -> MonitoringEvent:
        event = MonitoringEvent(
            run_id=self.run_id, trace_id=self.trace_id, event_type=event_type,
            status=status, agent_name=agent_name,
            orchestration_pattern=self.pattern, **kwargs,
        )
        if not self.enabled:
            return event
        self.events.append(event)
        for callback in self.callbacks:
            try:
                callback(event)
            except Exception:
                continue
        if self.enabled and self.verbosity == "verbose":
            print(f"[monitor] {event_type} {agent_name} {status}", flush=True)
        return event

    def start_agent(self, agent_name: str, dependencies: list[str] | None = None,
                    parent_agent: str = "") -> None:
        self._starts[agent_name].append(time.monotonic())
        self.emit("agent_started", "started", agent_name,
                  parent_agent=parent_agent,
                  metadata={"dependencies": dependencies or []})

    def finish_agent(self, agent_name: str, status: str = "completed",
                     output_summary: str = "", error: Exception | None = None) -> None:
        starts = self._starts.get(agent_name, [])
        started = starts.pop() if starts else None
        duration = (time.monotonic() - started) * 1000 if started is not None else None
        self.emit(
            f"agent_{status}", status, agent_name, duration_ms=duration,
            output_summary=output_summary,
            error_type=type(error).__name__ if error else "",
            error_message=str(error) if error else "",
        )

    def write_blackboard(self, agent_name: str, key: str, version: int,
                         success: bool = True) -> None:
        self.emit("blackboard_write", "completed" if success else "failed",
                  agent_name, metadata={"key": key, "version": version})

    def read_blackboard(self, agent_name: str, key: str) -> None:
        self.emit("blackboard_read", "completed", agent_name,
                  metadata={"key": key})

    def validation_result(self, stage: str, valid: bool,
                          metadata: dict[str, Any] | None = None,
                          error: Exception | None = None) -> None:
        """Publish validation results through the same callback stream."""
        self.emit(
            "validation_completed" if valid else "validation_failed",
            "completed" if valid else "failed",
            stage,
            output_summary="valid" if valid else "rejected",
            error_type=type(error).__name__ if error else "",
            error_message=str(error) if error else "",
            metadata=metadata or {},
        )

    def finalize(self, completed: bool = True) -> None:
        if not self.enabled:
            return
        self.emit("run_completed" if completed else "run_failed",
                  "completed" if completed else "failed")
        directory = self.output_dir / self._monitoring_directory_name()
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event in self.events:
                handle.write(event.model_dump_json() + "\n")
        metrics = self.agent_metrics()
        (directory / "agent_metrics.json").write_text(
            json.dumps(metrics, indent=2), encoding="utf-8")
        (directory / "summary.json").write_text(
            json.dumps(self.summary(), indent=2), encoding="utf-8")
        self._write_csv(directory / "agent_metrics.csv", metrics)
        self._write_visualizations(directory, metrics, self.events)

    def _monitoring_directory_name(self) -> str:
        return self.directory_name

    def agent_metrics(self) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[MonitoringEvent]] = defaultdict(list)
        for event in self.events:
            if event.event_type == "agent_completed":
                grouped[event.agent_name].append(event)
        result: dict[str, dict[str, Any]] = {}
        for agent, events in grouped.items():
            durations = [event.duration_ms for event in events if event.duration_ms is not None]
            failures = sum(event.status == "failed" for event in self.events
                           if event.agent_name == agent and event.event_type == "agent_failed")
            result[agent] = {
                "invocations": len(events),
                "average_duration_ms": sum(durations) / len(durations) if durations else None,
                "p95_duration_ms": sorted(durations)[max(0, int(len(durations) * .95) - 1)]
                if durations else None,
                "failure_count": failures,
                "retry_count": sum(event.retry_count for event in self.events if event.agent_name == agent),
                "tool_call_count": sum(event.event_type == "tool_called"
                                       for event in self.events if event.agent_name == agent),
                "validation_failure_count": sum(
                    event.event_type == "validation_failed"
                    for event in self.events if event.agent_name == agent),
            }
        return result

    def summary(self) -> dict[str, Any]:
        durations = [event.duration_ms for event in self.events
                     if event.event_type.startswith("agent_") and event.duration_ms is not None]
        intervals = [
            (event.timestamp.timestamp() - event.duration_ms / 1000, event.timestamp.timestamp())
            for event in self.events if event.event_type == "agent_completed"
            and event.duration_ms is not None
        ]
        maximum_concurrency = max(
            (sum(start <= point <= end for start, end in intervals)
             for point in [value for interval in intervals for value in interval]),
            default=0,
        )
        return {
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "orchestration_pattern": self.pattern,
            "event_count": len(self.events),
            "agent_metrics": self.agent_metrics(),
            "total_duration_ms": sum(durations) if durations else None,
            "maximum_observed_concurrency": maximum_concurrency,
            "blackboard_reads": sum(event.event_type == "blackboard_read" for event in self.events),
            "blackboard_writes": sum(event.event_type == "blackboard_write" for event in self.events),
            "tool_calls": sum(event.event_type == "tool_called" for event in self.events),
            "retries": sum(event.retry_count for event in self.events),
            "status": "completed" if any(event.event_type == "run_completed" for event in self.events)
            else "failed",
        }

    @staticmethod
    def _write_csv(path: Path, metrics: dict[str, dict[str, Any]]) -> None:
        fields = ["agent", "invocations", "average_duration_ms", "p95_duration_ms",
                  "failure_count", "retry_count", "tool_call_count", "validation_failure_count"]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for agent, values in metrics.items():
                writer.writerow({"agent": agent, **values})

    @staticmethod
    def _write_visualizations(directory: Path, metrics: dict[str, dict[str, Any]],
                              events: list[MonitoringEvent]) -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError:
            return
        agents = list(metrics)
        labels = ["duration_ms", "failures", "retries", "tools", "validation_failures"]
        values = [
            [metrics[agent]["average_duration_ms"] or np.nan for agent in agents],
            [metrics[agent]["failure_count"] for agent in agents],
            [metrics[agent]["retry_count"] for agent in agents],
            [metrics[agent]["tool_call_count"] for agent in agents],
            [metrics[agent]["validation_failure_count"] for agent in agents],
        ]
        for filename, title in [("agent_heatmap.png", "Agent execution heat map"),
                                ("system_heatmap.png", "System agent metrics heat map")]:
            fig, axis = plt.subplots(figsize=(max(5, len(agents) * 1.5), 3))
            if agents:
                image = axis.imshow(values, aspect="auto", cmap="YlOrRd")
                axis.set_xticks(range(len(agents)), agents, rotation=45, ha="right")
                axis.set_yticks(range(len(labels)), labels)
                fig.colorbar(image, ax=axis)
            else:
                axis.text(.5, .5, "No monitoring events recorded", ha="center", va="center")
                axis.set_axis_off()
            axis.set_title(title)
            fig.tight_layout()
            fig.savefig(directory / filename)
            plt.close(fig)


        fig, axis = plt.subplots(figsize=(10, max(3, len(agents) * .45)))
        # Completion timestamps and measured durations provide a truthful Gantt
        # view without storing raw prompts or requiring a tracing dependency.
        completed = [event for event in events if event.event_type == "agent_completed"
                     and event.duration_ms is not None]
        if completed:
            origin = min(event.timestamp.timestamp() - event.duration_ms / 1000
                         for event in completed)
            for index, event in enumerate(completed):
                start = event.timestamp.timestamp() - event.duration_ms / 1000 - origin
                axis.barh(index, event.duration_ms, left=start, color="tab:blue")
                axis.text(start, index, event.agent_name, va="center", ha="right", fontsize=8)
            axis.set_xlabel("Elapsed milliseconds")
            axis.set_yticks([])
            axis.set_title("Agent execution timeline")
        else:
            axis.text(.5, .5, "No agent execution events recorded", ha="center", va="center")
            axis.set_axis_off()
        fig.savefig(directory / "execution_timeline.png")
        plt.close(fig)


def build_adk_callbacks(monitor: Monitor) -> dict[str, Callback]:
    """Return ADK lifecycle callbacks for inputs, outputs, tools, and errors."""
    def context_name(callback_context: Any) -> str:
        agent = getattr(callback_context, "agent", None)
        return str(getattr(agent, "name", "") or getattr(
            callback_context, "agent_name", "adk"
        ))

    def state_keys(callback_context: Any) -> list[str]:
        state = getattr(callback_context, "state", None)
        if state is None:
            session = getattr(callback_context, "session", None)
            state = getattr(session, "state", None)
        return sorted(state.keys()) if isinstance(state, dict) else []

    def before_agent(callback_context: Any) -> None:
        name = context_name(callback_context)
        monitor.start_agent(name, parent_agent="adk")
        monitor.emit(
            "adk_agent_input", "started", name, input_summary="session state",
            metadata={"state_keys": state_keys(callback_context)},
        )

    def after_agent(callback_context: Any) -> None:
        name = context_name(callback_context)
        error = getattr(callback_context, "error", None)
        status = "failed" if error else "completed"
        monitor.finish_agent(
            name, status, output_summary="session state keys",
            error=error if isinstance(error, Exception) else None,
        )
        monitor.emit(
            "adk_agent_output", status, name, output_summary="session state keys",
            error_message=str(error) if error else "",
            metadata={"state_keys": state_keys(callback_context)},
        )

    def before_model(callback_context: Any, llm_request: Any) -> None:
        monitor.emit(
            "adk_model_started", "started", context_name(callback_context),
            input_summary=type(llm_request).__name__,
        )

    def after_model(callback_context: Any, llm_response: Any) -> None:
        monitor.emit(
            "adk_model_completed", "completed", context_name(callback_context),
            output_summary=type(llm_response).__name__,
        )

    def before_tool(callback_context: Any, tool: Any, args: Any) -> None:
        monitor.emit(
            "tool_called", "started", context_name(callback_context),
            input_summary=type(args).__name__,
            metadata={"tool": getattr(tool, "name", type(tool).__name__)},
        )

    def after_tool(callback_context: Any, tool: Any, tool_response: Any) -> None:
        monitor.emit(
            "tool_completed", "completed", context_name(callback_context),
            output_summary=type(tool_response).__name__,
            metadata={"tool": getattr(tool, "name", type(tool).__name__)},
        )

    return {
        "before_agent_callback": before_agent,
        "after_agent_callback": after_agent,
        "before_model_callback": before_model,
        "after_model_callback": after_model,
        "before_tool_callback": before_tool,
        "after_tool_callback": after_tool,
    }
