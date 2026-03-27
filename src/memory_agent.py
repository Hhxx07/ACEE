"""Bonus 1: Memory Agent — persistent cross-session memory."""

import os
import json
import time
from typing import Optional

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "memory.json")


def _load() -> list[dict]:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(memories: list[dict]):
    os.makedirs(os.path.dirname(MEMORY_FILE) or ".", exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2, ensure_ascii=False)


def save_memory(content: str, tags: list[str] | None = None) -> str:
    """Save a memory entry with timestamp and optional tags."""
    memories = _load()
    entry = {
        "id": len(memories) + 1,
        "content": content,
        "tags": tags or [],
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    memories.append(entry)
    _save(memories)
    return f"Memory saved (id={entry['id']}): {content[:50]}..."


def search_memory(query: str) -> list[dict]:
    """Search memories by keyword matching in content and tags."""
    memories = _load()
    query_lower = query.lower()
    results = []
    for m in memories:
        score = 0
        if query_lower in m["content"].lower():
            score += 2
        for tag in m.get("tags", []):
            if query_lower in tag.lower():
                score += 1
        if score > 0:
            results.append({**m, "_score": score})
    results.sort(key=lambda x: x["_score"], reverse=True)
    return results[:10]


def list_memories() -> list[dict]:
    """List all memories (most recent first)."""
    return list(reversed(_load()))


def delete_memory(memory_id: int) -> str:
    """Delete a memory by ID."""
    memories = _load()
    memories = [m for m in memories if m["id"] != memory_id]
    _save(memories)
    return f"Memory {memory_id} deleted."


def get_relevant_context(user_input: str) -> str:
    """Get relevant memories for the current conversation."""
    results = search_memory(user_input)
    if not results:
        return ""
    lines = ["[Relevant memories:]"]
    for m in results[:3]:
        lines.append(f"  - [{m['timestamp']}] {m['content']}")
    return "\n".join(lines)
