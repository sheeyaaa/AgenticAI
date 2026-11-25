"""In-memory typed event bus without shared mutable agent state."""
from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable, Literal, TypeVar
from pydantic import BaseModel
from prd_agents.models import BlackboardState, WriteLogEntry

Message = TypeVar("Message", bound=BaseModel)
Handler = Callable[[Message], Awaitable[None]]


class StateUpdate(BaseModel):
    """Typed handoff used by the message-passing architecture."""

    agent: str
    key: Literal[
        "document", "chunks", "requirement_points", "test_cases", "coverage",
        "critique", "history", "stale_iterations", "iteration", "token_stats",
        "selenium_scripts", "validation_report", "run_report",
    ]
    value: Any


class MessagePassingState:
    """State backend that validates updates and emits them through MessageBus.

    Agents only exchange StateUpdate messages; the backend is the sole owner of
    the validated snapshot and is interchangeable with the ADK Blackboard.
    """

    def __init__(self) -> None:
        self._state = BlackboardState()
        self.bus = MessageBus()
        self.messages: list[StateUpdate] = []

    def read(self, key: str) -> Any:
        if key not in BlackboardState.model_fields:
            raise KeyError(f"Unknown blackboard key: {key}")
        return getattr(self._state, key)

    def write(self, agent: str, key: str, value: Any) -> None:
        update = StateUpdate(agent=agent, key=key, value=value)
        self.messages.append(update)
        payload = self._state.model_dump()
        payload[update.key] = update.value
        candidate = BlackboardState.model_validate(payload)
        version = len(candidate.write_log) + 1
        candidate.write_log.append(
            WriteLogEntry(agent=agent, key=update.key, version=version)
        )
        self._state = candidate

    async def publish_update(self, update: StateUpdate) -> None:
        """Publish a validated handoff for subscribers that need live events."""
        self.messages.append(update)
        await self.bus.publish(update)

    def snapshot(self) -> BlackboardState:
        return self._state.model_copy(deep=True)


class MessageBus:
    def __init__(self) -> None:
        self._handlers: dict[type[BaseModel], list[Handler[BaseModel]]] = defaultdict(list)

    def subscribe(self, message_type: type[Message], handler: Handler[Message]) -> None:
        self._handlers[message_type].append(handler)  # type: ignore[arg-type]

    async def publish(self, message: Message) -> None:
        handlers = self._handlers.get(type(message), [])
        await asyncio.gather(*(handler(message) for handler in handlers))

    async def handoff(self, message: Message, handler: Handler[Message]) -> None:
        await handler(message)
