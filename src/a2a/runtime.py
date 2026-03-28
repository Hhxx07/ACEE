"""一个高层的分发函数"""

from __future__ import annotations

from .agents import MemoryA2AAgent, OrchestratorA2AAgent, ShellA2AAgent, ToolA2AAgent
from .models import A2ARequest, TaskState
from .transport import InProcessTransport


class A2ARuntime:
    """在这个总线上统一分发各种任务 -- 其他的接口变得简单"""

    def __init__(self):
        self._transport = InProcessTransport()
        self._orchestrator = OrchestratorA2AAgent()
        self._shell = ShellA2AAgent()
        self._tool = ToolA2AAgent()
        self._memory = MemoryA2AAgent()

        self._transport.register("orchestrator", self._orchestrator.handle)
        self._transport.register("shell", self._shell.handle)
        self._transport.register("tool", self._tool.handle)
        self._transport.register("memory", self._memory.handle)

    @staticmethod
    def _is_failure_response(response) -> bool:
        return bool(response.error) or response.state == TaskState.FAILED

    async def get_relevant_context(self, user_input: str) -> str:
        response = await self._transport.send(
            A2ARequest(
                to_agent="memory",
                action="get_relevant_context",
                payload={"user_input": user_input},
            )
        )
        if self._is_failure_response(response):
            return ""
        return str(response.artifacts.get("memory_context", ""))

    async def save_auto_memory(
        self,
        content: str,
        *,
        source: str = "manual",
        tags: list[str] | None = None,
        extra_tags: list[str] | None = None,
        metadata: dict | None = None,
        auto_tag: bool = True,
    ) -> dict:
        response = await self._transport.send(
            A2ARequest(
                to_agent="memory",
                action="save_auto_memory",
                payload={
                    "content": content,
                    "source": source,
                    "tags": tags or [],
                    "extra_tags": extra_tags or [],
                    "metadata": metadata or {},
                    "auto_tag": auto_tag,
                },
            )
        )
        if self._is_failure_response(response):
            return {}
        return response.artifacts.get("memory_record", {})

    async def classify_intent(self, user_input: str, history: list[dict] | None = None) -> dict:
        response = await self._transport.send(
            A2ARequest(
                to_agent="orchestrator",
                action="classify_intent",
                payload={"user_input": user_input, "history": history or []},
            )
        )
        if self._is_failure_response(response):
            return {
                "intent": "direct_answer",
                "reasoning": (response.error or {}).get("message", "A2A orchestrator failed."),
                "confidence": 0.0,
                "message": "Sorry, I had trouble understanding. Could you rephrase?",
            }
        return response.artifacts.get("classification", {})

    async def generate_command(self, task_description: str, user_input: str) -> dict:
        response = await self._transport.send(
            A2ARequest(
                to_agent="shell",
                action="generate_command",
                payload={"task_description": task_description, "user_input": user_input},
            )
        )
        if self._is_failure_response(response):
            return {
                "intent": "refuse",
                "command": "",
                "reason": (response.error or {}).get("message", "A2A shell failed."),
                "risk_level": "high",
                "safety_check": {"level": "deny", "reasons": ["A2A shell error"]},
            }
        return response.artifacts.get("command_result", {})

    async def handle_tool_task(self, task_description: str, user_input: str, on_output=None) -> str:
        response = await self._transport.send(
            A2ARequest(
                to_agent="tool",
                action="handle_task",
                payload={
                    "task_description": task_description,
                    "user_input": user_input,
                    "on_output": on_output,
                },
            )
        )
        if self._is_failure_response(response):
            err_msg = (response.error or {}).get("message", "A2A tool failure.")
            return f"[Tool Agent Error] {err_msg}"
        return str(response.artifacts.get("tool_output", ""))
