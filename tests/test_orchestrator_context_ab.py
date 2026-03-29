import json
import os
import sys
import unittest
import importlib
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

llm_client = importlib.import_module("src.llm_client")
orchestrator = importlib.import_module("src.orchestrator")


ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
ARTIFACT_FILE = ARTIFACTS_DIR / "orchestrator_context_ab.json"

# Fixed prompts for quick real-world comparison without mocking.
TEST_INPUTS = [
    "帮我查看当前目录下最大的5个文件，并按大小降序输出",
    "今天北京天气怎么样",
    "删除那个旧日志文件",
]


class TestOrchestratorContextAB(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_context_ab_output_saved(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            self.skipTest("OPENAI_API_KEY is not set; skipping real API A/B comparison test")

        results = []
        for user_input in TEST_INPUTS:
            comparison = await orchestrator.classify_intent_compare_context(user_input=user_input)
            results.append(comparison)

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": llm_client.MODEL,
            "sample_count": len(TEST_INPUTS),
            "samples": results,
        }

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACT_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.assertTrue(ARTIFACT_FILE.exists())
        self.assertEqual(payload["sample_count"], len(payload["samples"]))
        self.assertTrue(all("with_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("without_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("diff" in sample for sample in payload["samples"]))


if __name__ == "__main__":
    unittest.main()
