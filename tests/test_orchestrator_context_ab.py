import json
import os
import sys
import unittest
import importlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the same env-loading behavior as main entrypoint.
load_dotenv(PROJECT_ROOT / ".env")

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


def _build_summary(samples: list[dict]) -> dict:
    changed_samples = 0
    intent_changed_count = 0
    confidence_deltas: list[float] = []
    changed_field_counter: Counter[str] = Counter()

    for sample in samples:
        diff = sample.get("diff", {}) if isinstance(sample, dict) else {}
        changed = bool(diff.get("changed", False))
        if changed:
            changed_samples += 1

        changed_fields = diff.get("changed_fields", [])
        if isinstance(changed_fields, list):
            changed_field_counter.update(str(f) for f in changed_fields)
            if "intent" in changed_fields:
                intent_changed_count += 1

        with_ctx = sample.get("with_context", {}) if isinstance(sample, dict) else {}
        without_ctx = sample.get("without_context", {}) if isinstance(sample, dict) else {}
        with_conf = with_ctx.get("confidence") if isinstance(with_ctx, dict) else None
        without_conf = without_ctx.get("confidence") if isinstance(without_ctx, dict) else None
        if isinstance(with_conf, (int, float)) and isinstance(without_conf, (int, float)):
            confidence_deltas.append(float(with_conf) - float(without_conf))

    sample_count = len(samples)
    changed_rate = (changed_samples / sample_count) if sample_count else 0.0
    avg_conf_delta = (
        sum(confidence_deltas) / len(confidence_deltas)
        if confidence_deltas
        else 0.0
    )

    return {
        "changed_samples": changed_samples,
        "changed_rate": round(changed_rate, 4),
        "intent_changed_count": intent_changed_count,
        "avg_confidence_delta": round(avg_conf_delta, 4),
        "most_changed_fields": [
            {"field": field, "count": count}
            for field, count in changed_field_counter.most_common()
        ],
    }


class TestOrchestratorContextAB(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_context_ab_output_saved(self) -> None:
        run_id = uuid4().hex
        api_key = os.getenv("OPENAI_API_KEY")
        generated_at = datetime.now(timezone.utc).isoformat()

        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

        if not api_key:
            payload = {
                "run_id": run_id,
                "generated_at": generated_at,
                "model": llm_client.MODEL,
                "sample_count": len(TEST_INPUTS),
                "status": "skipped",
                "reason": "OPENAI_API_KEY is not set",
                "samples": [],
                "summary": _build_summary([]),
            }
            ARTIFACT_FILE.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.skipTest("OPENAI_API_KEY is not set; skipping real API A/B comparison test")

        results = []
        for user_input in TEST_INPUTS:
            comparison = await orchestrator.classify_intent_compare_context(user_input=user_input)
            results.append(comparison)

        payload = {
            "run_id": run_id,
            "generated_at": generated_at,
            "model": llm_client.MODEL,
            "sample_count": len(TEST_INPUTS),
            "status": "ok",
            "samples": results,
            "summary": _build_summary(results),
        }

        ARTIFACT_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.assertTrue(ARTIFACT_FILE.exists())
        self.assertEqual(payload["sample_count"], len(payload["samples"]))
        self.assertIn("summary", payload)
        self.assertTrue(all("with_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("without_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("diff" in sample for sample in payload["samples"]))


if __name__ == "__main__":
    unittest.main()
