"""A2A agent adapters over existing ACEE agent functions."""

from __future__ import annotations

from typing import Any

from .models import A2ARequest, A2AResponse, AgentCard, ErrorEnvelope, TaskState
from .. import orchestrator, shell_agent, tool_agent
from ..memory_agent import get_relevant_context, get_startup_context, save_memory_record


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
            startup_context = str(request.payload.get("startup_context", ""))
            optional_kwargs = {"startup_context": startup_context} if startup_context else {}
            result = await orchestrator.classify_intent(
                user_input,
                history,
                **optional_kwargs,
            )
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
        capabilities=["get_relevant_context", "get_startup_context", "save_auto_memory"],
    )

    async def handle(self, request: A2ARequest) -> A2AResponse:
        try:
            if request.action == "get_relevant_context":
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

            if request.action == "save_auto_memory":
                content = str(request.payload.get("content", "")).strip()
                if not content:
                    raise ValueError("Memory content cannot be empty.")

                tags = request.payload.get("tags")
                extra_tags = request.payload.get("extra_tags")
                source = str(request.payload.get("source", "manual"))
                auto_tag = bool(request.payload.get("auto_tag", True))
                metadata = request.payload.get("metadata")
                record = save_memory_record(
                    content,
                    tags=tags if isinstance(tags, list) else None,
                    auto_tag=auto_tag,
                    source=source,
                    extra_tags=extra_tags if isinstance(extra_tags, list) else None,
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
                return A2AResponse(
                    request_id=request.request_id,
                    task_id=request.task_id,
                    from_agent=self.card.name,
                    state=TaskState.COMPLETED,
                    artifacts={"memory_record": record},
                    state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
                )

            if request.action == "get_startup_context":
                raw_limit = request.payload.get("limit", 5)
                limit = int(raw_limit) if isinstance(raw_limit, (int, str)) else 5
                payload = get_startup_context(limit=max(limit, 0))
                return A2AResponse(
                    request_id=request.request_id,
                    task_id=request.task_id,
                    from_agent=self.card.name,
                    state=TaskState.COMPLETED,
                    artifacts={
                        "memory_context": payload.get("memory_context", ""),
                        "startup_memories": payload.get("memories", []),
                    },
                    state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.COMPLETED],
                )

            return _unsupported_action(request, self.card)

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
