import sys
import unittest
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

orchestrator = importlib.import_module("src.orchestrator")


class TestOrchestratorContextInjection(unittest.IsolatedAsyncioTestCase):
    async def test_context_mode_changes_system_prompt_content(self):
        llm_result = {
            "intent": "direct_answer",
            "reasoning": "llm",
            "confidence": 0.8,
            "message": "ok",
            "task_description": "",
        }

        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=False),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock, return_value=llm_result) as chat_json,
        ):
            await orchestrator.classify_intent("hello", history=[], use_context=True)
            with_prompt = chat_json.await_args.args[0][0]["content"]

            await orchestrator.classify_intent("hello", history=[], use_context=False)
            without_prompt = chat_json.await_args.args[0][0]["content"]

        self.assertIn("Context signals:", with_prompt)
        self.assertIn("Context signals:", without_prompt)
        self.assertIn("(not injected)", without_prompt)
        self.assertNotEqual(with_prompt, without_prompt)

    async def test_with_context_prompt_contains_decision_signals(self):
        llm_result = {
            "intent": "direct_answer",
            "reasoning": "llm",
            "confidence": 0.8,
            "message": "ok",
            "task_description": "",
        }

        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=False),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock, return_value=llm_result) as chat_json,
        ):
            await orchestrator.classify_intent("hello", history=[], use_context=True)

        prompt = chat_json.await_args.args[0][0]["content"]
        self.assertIn("directory_risk=", prompt)
        self.assertIn("entry_count=", prompt)
        self.assertIn("repo_tags=", prompt)

    async def test_offline_hit_includes_diagnostics(self):
        offline_result = {
            "intent": "shell_agent",
            "reasoning": "offline",
            "confidence": 0.9,
            "message": None,
            "task_description": "do x",
        }
        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=True),
            patch("src.orchestrator._classify_intent_offline", return_value=offline_result),
        ):
            result = await orchestrator.classify_intent("list files", history=[])

        self.assertTrue(result.get("offline_hit"))
        self.assertEqual(result.get("context_mode"), "with_context")

    async def test_llm_path_includes_diagnostics(self):
        llm_result = {
            "intent": "direct_answer",
            "reasoning": "llm",
            "confidence": 0.8,
            "message": "ok",
            "task_description": "",
        }
        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=False),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock, return_value=llm_result),
        ):
            result = await orchestrator.classify_intent("what is this", history=[], use_context=False)

        self.assertFalse(result.get("offline_hit"))
        self.assertEqual(result.get("context_mode"), "without_context")


if __name__ == "__main__":
    unittest.main()
