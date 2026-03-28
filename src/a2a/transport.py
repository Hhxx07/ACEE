"""Transport abstraction and in-process implementation for A2A."""

from __future__ import annotations

from typing import Awaitable, Callable

from .models import A2ARequest, A2AResponse, ErrorEnvelope, TaskState


A2AHandler = Callable[[A2ARequest], Awaitable[A2AResponse]]
RECOVERABLE_EXCEPTIONS = (RuntimeError, ValueError, TypeError, KeyError, OSError)


class InProcessTransport:
    """把任务按照AgentCard注册的名字分发给具体的agent"""

    def __init__(self):
        self._handlers: dict[str, A2AHandler] = {}

    def register(self, agent_name: str, handler: A2AHandler):
        #注册需要分发的地址
        self._handlers[agent_name] = handler

    async def send(self, request: A2ARequest) -> A2AResponse:
        #根据前面的注册信息分发内容
        handler = self._handlers.get(request.to_agent)
        if handler is None:
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent="transport",
                state=TaskState.FAILED,
                error=ErrorEnvelope(
                    code="agent_not_found",
                    message=f"Agent '{request.to_agent}' is not registered.",
                    retriable=False,
                ).to_dict(),
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.FAILED],
            )

        try:
            response = await handler(request)
        except RECOVERABLE_EXCEPTIONS as exc:
            return A2AResponse(
                request_id=request.request_id,
                task_id=request.task_id,
                from_agent=request.to_agent,
                state=TaskState.FAILED,
                error=ErrorEnvelope.from_exception(
                    code="agent_runtime_error",
                    exc=exc,
                    retriable=False,
                ).to_dict(),
                state_history=[TaskState.CREATED, TaskState.RUNNING, TaskState.FAILED],
            )

        response.request_id = request.request_id
        response.task_id = request.task_id
        response.protocol_version = request.protocol_version

        if response.state not in TaskState.ALL:
            response.state = TaskState.FAILED
            response.error = ErrorEnvelope(
                code="invalid_state",
                message=f"Handler returned invalid state for agent '{request.to_agent}'.",
                retriable=False,
                details={"state": response.state},
            ).to_dict()

        if not response.state_history:
            response.state_history = [TaskState.CREATED, TaskState.RUNNING]
        if response.state_history[-1] != response.state:
            response.state_history.append(response.state)

        return response
