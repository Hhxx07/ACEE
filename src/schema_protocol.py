"""Schema definitions for structured LLM JSON exchanges."""

from __future__ import annotations

from typing import Any

SCHEMA_KIND_ORCHESTRATOR = "orchestrator.classification"
SCHEMA_KIND_SHELL = "shell.command_plan"
SCHEMA_KIND_TOOL_CALL = "tool.function_call_result"

ENVELOPE_REQUIRED_KEYS = {"ok", "kind", "data", "error", "meta"}

SCHEMA_SPECS: dict[str, dict[str, Any]] = {
    SCHEMA_KIND_ORCHESTRATOR: {
        "required": {
            "intent": str,
            "reasoning": str,
            "confidence": (int, float),
            "message": (str, type(None)),
            "task_description": str,
        },
        "enums": {
            "intent": {
                "shell_agent",
                "tool_agent",
                "direct_answer",
                "clarification",
            },
        },
        "range": {
            "confidence": (0.0, 1.0),
        },
    },
    SCHEMA_KIND_SHELL: {
        "required": {
            "intent": str,
            "command": str,
            "reason": str,
            "risk_level": str,
            "clarification_options": list,
        },
        "enums": {
            "intent": {"run_command", "ask_clarification", "refuse"},
            "risk_level": {"low", "medium", "high"},
        },
        "range": {},
    },
    SCHEMA_KIND_TOOL_CALL: {
        "required": {
            "content": (str, type(None)),
            "tool_calls": list,
        },
        "enums": {},
        "range": {},
    },
}
