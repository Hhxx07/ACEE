"""Bonus 1: Memory Agent — persistent cross-session memory."""

import json
import os
import re
import tempfile
import time
from typing import Any

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "memory.json")

TAG_FALLBACK_MODE = os.getenv("ACEE_TAG_FALLBACK_MODE", "off").strip().lower()
TAG_CONFIDENCE_THRESHOLD = 0.45

TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    "shell": ("/", "cmd", "command", "shell", "terminal", "powershell", "bash"),
    "memory": ("!memory", "memory", "记忆", "回忆", "笔记"),
    "file": ("file", "files", "目录", "文件", "folder", "path", "ls", "dir"),
    "git": ("git", "commit", "push", "pull", "branch", "merge", "rebase"),
    "python": ("python", "pip", "conda", "venv", "py", "pylance"),
    "tool": ("tool", "api", "function", "调用", "工具"),
    "question": ("?", "吗", "什么", "怎么", "为何", "why", "how", "what"),
}

CONTROL_TAGS = {
    "direct_shell": ["shell", "command"],
    "memory_command": ["memory", "command"],
    "help_command": ["help", "command"],
    "orchestrated_input": ["orchestrator"],
    "memory_manual": ["memory", "manual"],
}


def _to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        lowered = tag.strip().lower()
        if not lowered or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(lowered)
    return normalized[:8]


def _extract_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_\-]+", text.lower())


def infer_tags(content: str, extra_tags: list[str] | None = None) -> tuple[list[str], float]:
    """Infer simple offline tags from text with a lightweight confidence score."""
    text = (content or "").strip()
    lowered = text.lower()
    inferred: list[str] = []
    matched = 0
    total = len(TAG_KEYWORDS)

    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            inferred.append(tag)
            matched += 1

    if text.startswith("/"):
        inferred.extend(["shell", "command"])
    elif text.startswith("!memory"):
        inferred.extend(["memory", "command"])
    elif text.endswith("?"):
        inferred.append("question")

    words = _extract_words(text)
    if any(w in {"rm", "del", "chmod", "sudo", "git"} for w in words):
        inferred.append("risk")

    if extra_tags:
        inferred.extend(extra_tags)

    confidence = matched / max(total, 1)
    if len(inferred) >= 3:
        confidence = max(confidence, 0.65)

    return _normalize_tags(inferred), min(confidence, 1.0)


def _fallback_needed(confidence: float) -> bool:
    return TAG_FALLBACK_MODE == "local_first" and confidence < TAG_CONFIDENCE_THRESHOLD


def _normalize_entry(entry: dict, fallback_id: int) -> dict:
    tags = _normalize_tags(_to_list(entry.get("tags")))
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return {
        "id": entry.get("id", fallback_id),
        "content": str(entry.get("content", "")),
        "tags": tags,
        "timestamp": str(entry.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))),
        "metadata": metadata,
    }


def _next_id(memories: list[dict]) -> int:
    max_id = 0
    for memory in memories:
        raw_id = memory.get("id")
        if isinstance(raw_id, int):
            max_id = max(max_id, raw_id)
    return max_id + 1


def _load() -> list[dict]:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
            if not isinstance(payload, list):
                return []
            return [_normalize_entry(item, idx + 1) for idx, item in enumerate(payload) if isinstance(item, dict)]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(memories: list[dict]):
    #把真正读写文本的函数定义在内部来让访问变得安全。
    os.makedirs(os.path.dirname(MEMORY_FILE) or ".", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="memory_", suffix=".json", dir=os.path.dirname(MEMORY_FILE) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(memories, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, MEMORY_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def save_memory_record(
    content: str,
    tags: list[str] | None = None,
    *,
    auto_tag: bool = False,
    source: str = "manual",
    extra_tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Save a memory entry and return the normalized record."""
    memories = _load()
    combined_tags = list(tags or [])
    confidence = 1.0
    tag_method = "manual"

    if auto_tag:
        source_tags = CONTROL_TAGS.get(source, [])
        inferred_tags, confidence = infer_tags(content, extra_tags=(extra_tags or []) + source_tags)
        combined_tags.extend(inferred_tags)
        tag_method = "local_rules"
    else:
        if extra_tags:
            combined_tags.extend(extra_tags)

    fallback_needed = _fallback_needed(confidence)
    merged_metadata = {
        "source": source,
        "tag_method": tag_method,
        "tag_confidence": round(confidence, 3),
        "fallback_mode": TAG_FALLBACK_MODE,
        "fallback_pending": fallback_needed,
    }
    if metadata:
        merged_metadata.update(metadata)

    entry = {
        "id": _next_id(memories),
        "content": content,
        "tags": _normalize_tags(combined_tags),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "metadata": merged_metadata,
    }
    memories.append(entry)
    _save(memories)
    return entry


def save_memory(
    content: str,
    tags: list[str] | None = None,
    *,
    auto_tag: bool = False,
    source: str = "manual",
    extra_tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Save a memory entry with timestamp and optional tags."""
    entry = save_memory_record(
        content,
        tags,
        auto_tag=auto_tag,
        source=source,
        extra_tags=extra_tags,
        metadata=metadata,
    )
    return f"Memory saved (id={entry['id']}): {content[:50]}..."


def search_memory(query: str) -> list[dict]:
    """Search memories by keyword matching in content and tags."""
    memories = _load()
    query_lower = query.lower()
    results = []
    for m in memories:
        score = 0
        content = str(m.get("content", ""))
        if query_lower in content.lower():
            score += 2
        for tag in _to_list(m.get("tags", [])):
            tag_lower = tag.lower()
            if query_lower == tag_lower:
                score += 2
            elif query_lower in tag_lower:
                score += 1
        if score > 0:
            normalized = _normalize_entry(m, fallback_id=0)
            results.append({**normalized, "_score": score})
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:10]


def get_relevant_context(user_input: str) -> str:
    """Get relevant memories for the current conversation."""
    results = search_memory(user_input)
    if not results:
        return ""
    lines = ["[Relevant memories:]"]
    for m in results[:3]:
        lines.append(f"  - [{m['timestamp']}] {m['content']}")
    return "\n".join(lines)
