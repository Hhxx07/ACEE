import json
import os
import sys
import unittest
import importlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if callable(load_dotenv):
    load_dotenv(PROJECT_ROOT / ".env")

llm_client = importlib.import_module("src.llm_client")
orchestrator = importlib.import_module("src.orchestrator")


ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
ARTIFACT_FILE = ARTIFACTS_DIR / "orchestrator_context_ab.json"

# Fixed prompts for quick real-world comparison without mocking.
TEST_INPUTS = [
    "我要在这个终端里设置一个名为 DEBUG_MODE 值为 true 的临时环境变量，然后打印出来确认。请给我命令。",
    "帮我写一个脚本命令，查看当前系统的内存使用情况。",
    "当前目录下有哪些可以被执行的脚本文件？我应该运行哪一个来启动当前的项目？",
    "帮我写一个命令，把当前目录下的所有日志文件压缩打包，并清理掉原文件。",
    "我刚写完代码，帮我把现在的改动生成一个合适的 Git Commit Message。",
    "我现在在哪个分支上？有没有忘记提交的文件？",
    "检查一下我当前的环境里有没有配置 HTTP 代理，或者有没有设置 JAVA_HOME 路径？",
    "分析我当前目录的项目结构和 Git 状态，告诉我接下来我需要运行什么命令来把最新的代码改动部署到测试环境？",
    "当前目录下有哪些可以被执行的脚本文件？我应该运行哪一个来启动当前的项目？"
]


def _write_artifact(payload: dict) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_summary(samples: list[dict]) -> dict:
    changed_samples = 0
    intent_changed_count = 0
    confidence_deltas: list[float] = []
    field_counts: dict[str, int] = {}
    with_context_offline_hits = 0
    without_context_offline_hits = 0
    llm_path_samples = 0
    llm_path_changed = 0

    for sample in samples:
        diff = sample.get("diff", {})
        if diff.get("changed"):
            changed_samples += 1

        with_ctx = sample.get("with_context", {})
        without_ctx = sample.get("without_context", {})

        with_offline = bool(with_ctx.get("offline_hit"))
        without_offline = bool(without_ctx.get("offline_hit"))
        if with_offline:
            with_context_offline_hits += 1
        if without_offline:
            without_context_offline_hits += 1
        if not with_offline and not without_offline:
            llm_path_samples += 1
            if diff.get("changed"):
                llm_path_changed += 1

        if with_ctx.get("intent") != without_ctx.get("intent"):
            intent_changed_count += 1

        a = with_ctx.get("confidence")
        b = without_ctx.get("confidence")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            confidence_deltas.append(float(a) - float(b))

        for field in diff.get("changed_fields", []):
            field_counts[field] = field_counts.get(field, 0) + 1

    sample_count = len(samples)
    return {
        "changed_samples": changed_samples,
        "changed_rate": round(changed_samples / sample_count, 4) if sample_count else 0.0,
        "intent_changed_count": intent_changed_count,
        "with_context_offline_hit_rate": (
            round(with_context_offline_hits / sample_count, 4) if sample_count else 0.0
        ),
        "without_context_offline_hit_rate": (
            round(without_context_offline_hits / sample_count, 4) if sample_count else 0.0
        ),
        "llm_only_changed_rate": (
            round(llm_path_changed / llm_path_samples, 4) if llm_path_samples else 0.0
        ),
        "avg_confidence_delta": (
            round(sum(confidence_deltas) / len(confidence_deltas), 4)
            if confidence_deltas
            else 0.0
        ),
        "most_changed_fields": sorted(
            field_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        ),
    }


class TestOrchestratorContextAB(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_context_ab_output_saved(self) -> None:
        run_id = uuid.uuid4().hex[:12]
        base_payload = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": llm_client.MODEL,
            "sample_count": len(TEST_INPUTS),
            "notes": "real_api_ab_compare",
        }

        if not os.getenv("OPENAI_API_KEY"):
            payload = {
                **base_payload,
                "status": "skipped",
                "reason": "OPENAI_API_KEY is not set",
                "samples": [],
                "summary": {
                    "changed_samples": 0,
                    "changed_rate": 0.0,
                    "intent_changed_count": 0,
                    "avg_confidence_delta": 0.0,
                    "most_changed_fields": [],
                },
            }
            _write_artifact(payload)
            self.skipTest("OPENAI_API_KEY is not set; skipping real API A/B comparison test")

        results = []
        for idx, user_input in enumerate(TEST_INPUTS, start=1):
            comparison = await orchestrator.classify_intent_compare_context(user_input=user_input)
            comparison["sample_id"] = idx
            comparison["verdict"] = "changed" if comparison.get("diff", {}).get("changed") else "same"
            results.append(comparison)

        payload = {
            **base_payload,
            "status": "completed",
            "samples": results,
            "summary": _build_summary(results),
        }

        _write_artifact(payload)

        self.assertTrue(ARTIFACT_FILE.exists())
        self.assertEqual(payload["sample_count"], len(payload["samples"]))
        self.assertTrue(all("with_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("without_context" in sample for sample in payload["samples"]))
        self.assertTrue(all("diff" in sample for sample in payload["samples"]))


if __name__ == "__main__":
    unittest.main()
