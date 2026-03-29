import sys
import unittest
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

runtime_mod = importlib.import_module("src.a2a.runtime")
agents_mod = importlib.import_module("src.a2a.agents")
models_mod = importlib.import_module("src.a2a.models")
shell_agent = importlib.import_module("src.shell_agent")
tool_agent = importlib.import_module("src.tool_agent")
tui_mod = importlib.import_module("src.tui")


class TestHistoryRuntimePayload(unittest.IsolatedAsyncioTestCase):
    async def test_generate_command_includes_history_payload(self):
        runtime = runtime_mod.A2ARuntime()
        runtime._transport.send = AsyncMock(
            return_value=models_mod.A2AResponse(
                request_id="r1",
                task_id="t1",
                from_agent="shell",
                state=models_mod.TaskState.COMPLETED,
                artifacts={"command_result": {"intent": "run_command", "command": "echo ok"}},
            )
        )

        history = [{"role": "user", "content": "first"}]
        await runtime.generate_command("task", "now", history=history)

        sent_req = runtime._transport.send.await_args.args[0]
        self.assertEqual(sent_req.payload.get("history"), history)

    async def test_handle_tool_task_includes_history_payload(self):
        runtime = runtime_mod.A2ARuntime()
        runtime._transport.send = AsyncMock(
            return_value=models_mod.A2AResponse(
                request_id="r2",
                task_id="t2",
                from_agent="tool",
                state=models_mod.TaskState.COMPLETED,
                artifacts={"tool_output": "ok"},
            )
        )

        history = [{"role": "assistant", "content": "second"}]
        await runtime.handle_tool_task("task", "now", history=history)

        sent_req = runtime._transport.send.await_args.args[0]
        self.assertEqual(sent_req.payload.get("history"), history)


class TestHistoryA2AForwarding(unittest.IsolatedAsyncioTestCase):
    async def test_shell_agent_forward_history(self):
        agent = agents_mod.ShellA2AAgent()
        history = [{"role": "user", "content": "prev"}]
        req = models_mod.A2ARequest(
            to_agent="shell",
            action="generate_command",
            payload={
                "user_input": "now",
                "task_description": "do now",
                "history": history,
            },
        )

        with patch("src.a2a.agents.shell_agent.generate_command", new_callable=AsyncMock) as fn:
            fn.return_value = {"intent": "run_command", "command": "echo hi"}
            await agent.handle(req)

        fn.assert_awaited_once_with("do now", "now", history=history)

    async def test_tool_agent_forward_history(self):
        agent = agents_mod.ToolA2AAgent()
        history = [{"role": "assistant", "content": "prev answer"}]
        req = models_mod.A2ARequest(
            to_agent="tool",
            action="handle_task",
            payload={
                "user_input": "now",
                "task_description": "do now",
                "history": history,
            },
        )

        with patch("src.a2a.agents.tool_agent.handle_task", new_callable=AsyncMock) as fn:
            fn.return_value = "done"
            await agent.handle(req)

        args = fn.await_args.args
        kwargs = fn.await_args.kwargs
        self.assertEqual(args[0], "do now")
        self.assertEqual(args[1], "now")
        self.assertIsNone(kwargs.get("on_output"))
        self.assertEqual(kwargs.get("history"), history)


class TestHistoryPromptInjection(unittest.IsolatedAsyncioTestCase):
    async def test_shell_prompt_contains_recent_history(self):
        history = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "tool", "content": "ignore"},
            {"role": "assistant", "content": 123},
            {"role": "user", "content": "u2"},
        ]

        with patch("src.shell_agent.llm_client.chat_json", new_callable=AsyncMock) as chat_json:
            chat_json.return_value = {
                "intent": "run_command",
                "command": "echo ok",
                "reason": "test",
                "risk_level": "low",
                "clarification_options": [],
            }
            await shell_agent.generate_command("task", "now", history=history)

        messages = chat_json.await_args.args[0]
        self.assertEqual(messages[1:4], [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("Original user request: now", messages[-1]["content"])

    async def test_tool_prompt_contains_recent_history(self):
        history = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "ignore"},
            "bad",
            {"role": "assistant", "content": "a2"},
        ]

        with (
            patch("src.tool_agent.list_tools", return_value=[{"name": "dummy"}]),
            patch("src.tool_agent.llm_client.chat_function_call", new_callable=AsyncMock) as call_fn,
        ):
            call_fn.return_value = {"content": "done"}
            await tool_agent.handle_task("task", "now", history=history)

        messages = call_fn.await_args.args[0]
        self.assertEqual(messages[1:4], [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
        ])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertIn("User request: now", messages[-1]["content"])


class TestTuiHistorySanitization(unittest.TestCase):
    def test_history_for_llm_filters_and_truncates(self):
        app = tui_mod.AgentCLI()
        app.conversation_history = [
            {"role": "assistant", "content": "startup"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "drop"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "current"},
        ]

        result = app._history_for_llm(limit=3, include_current=False)
        self.assertEqual(result, [
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        ])


if __name__ == "__main__":
    unittest.main()
