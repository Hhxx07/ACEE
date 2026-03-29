import sys
import unittest
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

orchestrator = importlib.import_module("src.orchestrator")


class TestOrchestratorOfflineFirst(unittest.IsolatedAsyncioTestCase):
    async def test_offline_hit_bypasses_llm(self) -> None:
        offline_result = {
            "intent": "shell_agent",
            "reasoning": "Offline pre-classifier hit",
            "confidence": 0.93,
            "message": None,
            "task_description": "列出当前目录",
        }

        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=True),
            patch("src.orchestrator._classify_intent_offline", return_value=offline_result),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock) as chat_json,
        ):
            result = await orchestrator.classify_intent("列出当前目录")

        self.assertEqual(result["intent"], "shell_agent")
        self.assertEqual(result["task_description"], "列出当前目录")
        chat_json.assert_not_awaited()

    async def test_offline_miss_falls_back_to_llm(self) -> None:
        llm_result = {
            "intent": "direct_answer",
            "reasoning": "LLM fallback",
            "confidence": 0.66,
            "message": "这是一个普通问题",
            "task_description": "",
        }

        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=True),
            patch("src.orchestrator._classify_intent_offline", return_value=None),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock, return_value=llm_result) as chat_json,
        ):
            result = await orchestrator.classify_intent("今天北京天气怎么样")

        self.assertEqual(result["intent"], "direct_answer")
        chat_json.assert_awaited_once()

    async def test_offline_clarification_bypasses_llm(self) -> None:
        offline_result = {
            "intent": "clarification",
            "reasoning": "Offline pre-classifier needs clarification",
            "confidence": 0.85,
            "message": "缺少明确目标路径",
            "task_description": "",
        }

        with (
            patch("src.orchestrator._resolve_orch_offline_first", return_value=True),
            patch("src.orchestrator._classify_intent_offline", return_value=offline_result),
            patch("src.orchestrator.llm_client.chat_json", new_callable=AsyncMock) as chat_json,
        ):
            result = await orchestrator.classify_intent("删除那个文件")

        self.assertEqual(result["intent"], "clarification")
        self.assertTrue(result["message"])
        chat_json.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
