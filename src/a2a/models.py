"""Core A2A protocol models for in-process communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class AgentCard:
    """A2A capability declaration for an agent endpoint."""

    name: str
    description: str
    capabilities: list[str]
    protocol_version: str = "a2a.v0"


class TaskState:
    """Task lifecycle states aligned with A2A semantics."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = {CREATED, RUNNING, WAITING, COMPLETED, FAILED, CANCELLED}


@dataclass
class ErrorEnvelope:
    """Protocol-level error envelope for A2A responses."""

    code: str
    message: str
    retriable: bool = False
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retriable": self.retriable,
            "details": self.details or {},
        }

    @staticmethod
    def from_exception(code: str, exc: Exception, retriable: bool = False) -> "ErrorEnvelope":
        return ErrorEnvelope(
            code=code,
            message=str(exc) or exc.__class__.__name__,
            retriable=retriable,
            details={"exception_type": exc.__class__.__name__},
        )


@dataclass
class A2ARequest:
    """A2A request envelope."""

    to_agent: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    from_agent: str = "tui"
    request_id: str = field(default_factory=lambda: _new_id("req"))
    task_id: str = field(default_factory=lambda: _new_id("task"))
    timestamp: str = field(default_factory=_utc_now)
    protocol_version: str = "a2a.v0"
    trace: dict[str, Any] | None = None


@dataclass
class A2AResponse:
    """A2A response envelope."""

    request_id: str
    task_id: str
    from_agent: str
    state: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    state_history: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_utc_now)
    protocol_version: str = "a2a.v0"

    def __post_init__(self):
        if self.state not in TaskState.ALL:
            raise ValueError(f"Unsupported task state: {self.state}")
        if not self.state_history:
            self.state_history = [TaskState.CREATED, TaskState.RUNNING, self.state]
        elif self.state_history[-1] != self.state:
            self.state_history.append(self.state)

TASK_STATES = TaskState.ALL
