"""A2A agent adapters over existing ACEE agent functions."""

from __future__ import annotations

from typing import Any

from .models import A2ARequest, A2AResponse, AgentCard, ErrorEnvelope, TaskState
from .. import orchestrator, shell_agent, tool_agent
from ..memory_agent import get_relevant_context


RECOVERABLE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    ImportError,
    AttributeError,
)


'''
给每个agent写agnetcard（介绍名片）和调用函数当做接口
相当于在这里注册agent库
'''

class OrchestratorA2AAgent:
    card = AgentCard(
        name="orchestrator",
        description="Classifies user intent and proposes routing target.",
        capabilities=["classify_intent"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        if request.action != "classify_intent":
            return _unsupported_action(request, self.card)

        try:
            user_input = str(request.payload.get("user_input", ""))
            history = request.payload.get("history") or []
            result = await orchestrator.classify_intent(user_input, history)
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=self.card.name,
                state=TaskState.COMPLETED,
                artifacts={"classification": result},
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
            )
        except RECOVERABLE_EXCEPTIONS as exc:
            return _agent_exception(request, self.card, exc)


class ShellA2AAgent:
    card = AgentCard(
        name="shell",
        description="Generates shell commands with risk and safety metadata.",
        capabilities=["generate_command"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        if request.action != "generate_command":
            return _unsupported_action(request, self.card)

        try:
            user_input = str(request.payload.get("user_input", ""))
            task_description = str(request.payload.get("task_description", user_input))
            result = await shell_agent.generate_command(task_description, user_input)
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=self.card.name,
                state=TaskState.COMPLETED,
                artifacts={"command_result": result},
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
            )
        except RECOVERABLE_EXCEPTIONS as exc:
            return _agent_exception(request, self.card, exc)


class ToolA2AAgent:
    card = AgentCard(
        name="tool",
        description="Executes tool-based tasks using function-calling loop.",
        capabilities=["handle_task"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        if request.action != "handle_task":
            return _unsupported_action(request, self.card)

        try:
            user_input = str(request.payload.get("user_input", ""))
            task_description = str(request.payload.get("task_description", user_input))
            on_output = request.payload.get("on_output")
            result = await tool_agent.handle_task(task_description, user_input, on_output)
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=self.card.name,
                state=TaskState.COMPLETED,
                artifacts={"tool_output": result},
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
            )
        except RECOVERABLE_EXCEPTIONS as exc:
            return _agent_exception(request, self.card, exc)


class MemoryA2AAgent:
    card = AgentCard(
        name="memory",
        description="Provides relevant memory context for a user input.",
        capabilities=["get_relevant_context"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        if request.action != "get_relevant_context":
            return _unsupported_action(request, self.card)

        try:
            user_input = str(request.payload.get("user_input", ""))
            result = get_relevant_context(user_input)
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=self.card.name,
                state=TaskState.COMPLETED,
                artifacts={"memory_context": result},
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
            )
        except RECOVERABLE_EXCEPTIONS as exc:
            return _agent_exception(request, self.card, exc)


def _unsupported_action(request: A2ARequest, card: AgentCard) -> A2AResponse:
    return A2AResponse(
        request_id=request.request_id,
        task_id=request.task_id,
        from_agent=card.name,
        state=TaskState.FAILED,
        error=ErrorEnvelope(
            code="unsupported_action",
            message=f"Action '{request.action}' is not supported by agent '{card.name}'.",
            retriable=False,
        ).to_dict(),
        state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.FAILED],
        artifacts={"agent_card": _card_to_dict(card)},
    )


def _agent_exception(request: A2ARequest, card: AgentCard, exc: Exception) -> A2AResponse:
    return A2AResponse(
        request_id=request.request_id,
        task_id=request.task_id,
        from_agent=card.name,
        state=TaskState.FAILED,
        error=ErrorEnvelope.from_exception(
            code="agent_handler_error",
            exc=exc,
            retriable=False,
        ).to_dict(),
        state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.FAILED],
    )


def _card_to_dict(card: AgentCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "description": card.description,
        "capabilities": card.capabilities,
        "protocol_version": card.protocol_version,
    }
