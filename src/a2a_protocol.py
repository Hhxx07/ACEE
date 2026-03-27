"""Bonus 3: A2A (Agent-to-Agent) Protocol — standardized inter-agent communication.

Defines a structured message format for agents to communicate with each other,
enabling decoupled, inspectable, and extensible multi-agent orchestration.

Message format follows a request/response pattern inspired by JSON-RPC and HTTP:

    AgentMessage:
        id:         Unique message ID
        from_agent: Sender agent name
        to_agent:   Receiver agent name
        type:       "request" | "response" | "error" | "event"
        method:     Action being requested (e.g., "generate_command", "execute_tool")
        payload:    Task-specific data (dict)
        metadata:   Optional metadata (timestamps, correlation IDs, etc.)
"""

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class AgentMessage:
    """Standardized message exchanged between agents."""

    from_agent: str
    to_agent: str
    type: str  # "request" | "response" | "error" | "event"
    method: str
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def reply(self, payload: dict, msg_type: str = "response") -> "AgentMessage":
        """Create a response message to this message."""
        return AgentMessage(
            from_agent=self.to_agent,
            to_agent=self.from_agent,
            type=msg_type,
            method=self.method,
            payload=payload,
            metadata={"in_reply_to": self.id},
        )

    def error(self, error_msg: str, code: str = "AGENT_ERROR") -> "AgentMessage":
        """Create an error response to this message."""
        return AgentMessage(
            from_agent=self.to_agent,
            to_agent=self.from_agent,
            type="error",
            method=self.method,
            payload={"error": error_msg, "code": code},
            metadata={"in_reply_to": self.id},
        )


class AgentBus:
    """Simple message bus for agent-to-agent communication.

    Agents register handlers for methods they support.
    The bus routes messages to the appropriate handler.
    """

    def __init__(self):
        self._handlers: dict[str, dict[str, Any]] = {}  # agent_name -> {method -> handler}
        self._message_log: list[AgentMessage] = []
        self._event_listeners: list[Any] = []

    def register_agent(self, agent_name: str, handlers: dict[str, Any]):
        """Register an agent with its supported method handlers.

        handlers: {method_name: async_callable}
        """
        self._handlers[agent_name] = handlers

    def add_event_listener(self, listener):
        """Add a listener that receives all messages (for logging/debugging)."""
        self._event_listeners.append(listener)

    async def send(self, message: AgentMessage) -> AgentMessage:
        """Send a message to an agent and await the response."""
        self._message_log.append(message)

        # Notify event listeners
        for listener in self._event_listeners:
            try:
                await listener(message)
            except Exception:
                pass

        target = message.to_agent
        if target not in self._handlers:
            resp = message.error(f"Agent '{target}' not found", "AGENT_NOT_FOUND")
            self._message_log.append(resp)
            return resp

        method = message.method
        handlers = self._handlers[target]
        if method not in handlers:
            resp = message.error(
                f"Agent '{target}' does not support method '{method}'",
                "METHOD_NOT_FOUND",
            )
            self._message_log.append(resp)
            return resp

        handler = handlers[method]
        try:
            result = await handler(message)
            if isinstance(result, AgentMessage):
                resp = result
            else:
                resp = message.reply(result if isinstance(result, dict) else {"result": result})
        except Exception as e:
            resp = message.error(str(e))

        self._message_log.append(resp)

        # Notify event listeners
        for listener in self._event_listeners:
            try:
                await listener(resp)
            except Exception:
                pass

        return resp

    def get_message_log(self) -> list[dict]:
        """Get the full message log for debugging."""
        return [m.to_dict() for m in self._message_log]

    def get_registered_agents(self) -> dict[str, list[str]]:
        """List registered agents and their supported methods."""
        return {name: list(handlers.keys()) for name, handlers in self._handlers.items()}


# Global message bus instance
bus = AgentBus()


def create_request(
    from_agent: str,
    to_agent: str,
    method: str,
    **payload,
) -> AgentMessage:
    """Helper to create a request message."""
    return AgentMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        type="request",
        method=method,
        payload=payload,
    )
