"""
Append-only JSONL debug logging for LLM structured responses.
验证llm返回的json是否满足条件，允许后面多加东西
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _as_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_log_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    return root / "logs" / "llm_responses.jsonl"


def _resolve_log_path() -> Path:
    override = os.getenv("ACEE_LLM_DEBUG_LOG_PATH")
    if override:
        return Path(override)
    return _default_log_path()


def debug_log_enabled() -> bool:
    return _as_bool(os.getenv("ACEE_LLM_DEBUG_LOG"), default=False)


def append_llm_record(record: dict[str, Any]) -> None:
    """Persist a single JSONL record if debug logging is enabled."""
    if not debug_log_enabled():
        return

    path = _resolve_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **record,
    }

    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
