"""ADK-session-backed blackboard with validated, versioned writes."""
from __future__ import annotations
from threading import RLock
from typing import Any, Protocol
from .models import BlackboardState, WriteLogEntry


class SessionLike(Protocol):
    state: dict[str, Any]


class Blackboard:
    def __init__(self, session: SessionLike | None = None, monitor: Any = None,
                 agent_name: str = "blackboard") -> None:
        self._session = session
        self._monitor = monitor
        self._agent_name = agent_name
        self._lock = RLock()
        initial = dict(getattr(session, "state", {}) or {})
        self.state = BlackboardState.model_validate(initial)
        if session is not None:
            session.state.update(self.state.model_dump(mode="json"))

    @classmethod
    def from_context(cls, ctx: Any, monitor: Any = None,
                     agent_name: str = "blackboard") -> "Blackboard":
        """Create a board from an ADK callback context's session state."""
        session = getattr(ctx, "session", None)
        if session is None or not hasattr(session, "state"):
            raise TypeError("ADK context must expose session.state.")
        return cls(session=session, monitor=monitor, agent_name=agent_name)

    def read(self, key: str) -> Any:
        with self._lock:
            if key not in BlackboardState.model_fields:
                raise KeyError(f"Unknown blackboard key: {key}")
            value = getattr(self.state, key)
            if self._monitor:
                self._monitor.read_blackboard(self._agent_name, key)
            return value

    def write(self, agent: str, key: str, value: Any) -> None:
        with self._lock:
            if key not in BlackboardState.model_fields or key == "write_log":
                raise KeyError(f"Unknown or protected blackboard key: {key}")
            payload = self.state.model_dump()
            payload[key] = value
            candidate = BlackboardState.model_validate(payload)
            version = len(candidate.write_log) + 1
            candidate.write_log.append(WriteLogEntry(agent=agent, key=key, version=version))
            self.state = candidate
            if self._session is not None:
                self._session.state.update(self.state.model_dump(mode="json"))
            if self._monitor:
                self._monitor.write_blackboard(agent, key, version)

    def write_state_delta(self, agent: str, state_delta: dict[str, Any]) -> None:
        """Apply an ADK state_delta using the same per-key validation path."""
        if not isinstance(state_delta, dict):
            raise TypeError("state_delta must be a dictionary.")
        for key, value in state_delta.items():
            self.write(agent, key, value)

    def snapshot(self) -> BlackboardState:
        with self._lock:
            return self.state.model_copy(deep=True)
