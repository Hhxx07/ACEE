"""
Validation helpers for LLM JSON responses.
检验返回信息
"""

from __future__ import annotations

import json
from typing import Any

from .schema_protocol import (
    ENVELOPE_REQUIRED_KEYS,
    SCHEMA_KIND_ORCHESTRATOR,
    SCHEMA_KIND_TOOL_CALL,
    SCHEMA_SPECS,
)


def _err(code: str, message: str, details: dict[str, Any], retryable: bool) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "retryable": retryable,
    }


def format_user_error(error: dict[str, Any]) -> str:
    """Build a medium-detail user-friendly error summary."""
    code = str(error.get("code", "unknown_error"))
    message = str(error.get("message", "LLM response validation failed."))
    details = error.get("details", {})
    if isinstance(details, dict) and details:
        summary = ", ".join(f"{k}={v}" for k, v in list(details.items())[:4])
        return f"{message} (code={code}; {summary})"
    return f"{message} (code={code})"


def build_retry_prompt(schema_kind: str, error: dict[str, Any]) -> str:
    """Generate retry instruction for model after parse/validation failure."""
    return (
        "Your previous output did not match the required JSON schema. "
        f"schema_kind={schema_kind}. "
        f"error_code={error.get('code')}. "
        "Output ONLY one valid JSON object, with no extra text."
    )


def normalize_to_envelope(data: dict[str, Any], schema_kind: str) -> dict[str, Any]:
    """Accept legacy payload shape and normalize into the common envelope."""
    if ENVELOPE_REQUIRED_KEYS.issubset(data.keys()):
        normalized = data.copy()
        normalized.setdefault("meta", {})
        return normalized

    return {
        "ok": True,
        "kind": schema_kind,
        "data": data,
        "error": None,
        "meta": {"normalized_from_legacy": True},
    }


def validate_envelope(envelope: dict[str, Any], schema_kind: str) -> dict[str, Any] | None:
    if not isinstance(envelope.get("ok"), bool):
        return _err(
            "wrong_type",
            "Envelope field 'ok' must be boolean.",
            {"field": "ok"},
            True,
        )

    if not isinstance(envelope.get("kind"), str):
        return _err(
            "wrong_type",
            "Envelope field 'kind' must be string.",
            {"field": "kind"},
            True,
        )

    if envelope.get("kind") != schema_kind:
        return _err(
            "enum_invalid",
            "Envelope kind does not match expected schema.",
            {"expected": schema_kind, "actual": envelope.get("kind")},
            True,
        )

    if not isinstance(envelope.get("data"), dict):
        return _err(
            "wrong_type",
            "Envelope field 'data' must be object.",
            {"field": "data"},
            True,
        )

    error_field = envelope.get("error")
    if error_field is not None and not isinstance(error_field, dict):
        return _err(
            "wrong_type",
            "Envelope field 'error' must be null or object.",
            {"field": "error"},
            True,
        )

    if not isinstance(envelope.get("meta"), dict):
        return _err(
            "wrong_type",
            "Envelope field 'meta' must be object.",
            {"field": "meta"},
            True,
        )

    return None


def validate_payload(payload: dict[str, Any], schema_kind: str) -> dict[str, Any] | None:
    spec = SCHEMA_SPECS.get(schema_kind)
    if not spec:
        return _err(
            "schema_not_found",
            "No schema is configured for this schema kind.",
            {"schema_kind": schema_kind},
            False,
        )

    for field, expected_type in spec["required"].items():
        if field not in payload:
            return _err(
                "missing_field",
                f"Required field '{field}' is missing.",
                {"field": field},
                True,
            )
        if not isinstance(payload[field], expected_type):
            return _err(
                "wrong_type",
                f"Field '{field}' has invalid type.",
                {
                    "field": field,
                    "expected": str(expected_type),
                    "actual": type(payload[field]).__name__,
                },
                True,
            )

    for field, allowed_values in spec["enums"].items():
        if field in payload and payload[field] not in allowed_values:
            return _err(
                "enum_invalid",
                f"Field '{field}' has unsupported value.",
                {"field": field, "value": payload[field]},
                True,
            )

    for field, (min_value, max_value) in spec["range"].items():
        if field in payload:
            value = payload[field]
            if isinstance(value, (int, float)) and not (min_value <= value <= max_value):
                return _err(
                    "constraint_failed",
                    f"Field '{field}' is out of allowed range.",
                    {"field": field, "min": min_value, "max": max_value, "actual": value},
                    True,
                )

    if schema_kind == SCHEMA_KIND_ORCHESTRATOR:
        intent = payload.get("intent")
        message = payload.get("message")
        task_description = payload.get("task_description")

        if intent in {"direct_answer", "clarification"}:
            if not isinstance(message, str) or not message.strip():
                return _err(
                    "constraint_failed",
                    "Field 'message' must be a non-empty string for this intent.",
                    {"field": "message", "intent": intent},
                    True,
                )

        if intent in {"shell_agent", "tool_agent"}:
            if not isinstance(task_description, str) or not task_description.strip():
                return _err(
                    "constraint_failed",
                    "Field 'task_description' must be a non-empty string for this intent.",
                    {"field": "task_description", "intent": intent},
                    True,
                )

    return None


def validate_json_text(
    raw_text: str,
    schema_kind: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Parse raw text, normalize to envelope, and validate against schema."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, _err(
            "json_malformed",
            "Response is not valid JSON.",
            {"pos": exc.pos, "msg": exc.msg},
            True,
        )

    if not isinstance(parsed, dict):
        return None, _err(
            "wrong_type",
            "Root JSON value must be an object.",
            {"actual": type(parsed).__name__},
            True,
        )

    envelope = normalize_to_envelope(parsed, schema_kind)

    envelope_error = validate_envelope(envelope, schema_kind)
    if envelope_error is not None:
        return None, envelope_error

    payload_error = validate_payload(envelope["data"], schema_kind)
    if payload_error is not None:
        return None, payload_error

    return envelope, None


def validate_tool_call_response(result: dict[str, Any]) -> dict[str, Any] | None:
    """Validate function-call response shape returned by llm_client."""
    payload_error = validate_payload(result, SCHEMA_KIND_TOOL_CALL)
    if payload_error is not None:
        return payload_error

    tool_calls = result.get("tool_calls", [])
    for index, tool_call in enumerate(tool_calls):
        if not isinstance(tool_call, dict):
            return _err(
                "wrong_type",
                "Each tool call must be an object.",
                {"index": index},
                True,
            )

        for field in ("id", "type", "function"):
            if field not in tool_call:
                return _err(
                    "missing_field",
                    f"Tool call field '{field}' is missing.",
                    {"index": index, "field": field},
                    True,
                )

        function_obj = tool_call.get("function")
        if not isinstance(function_obj, dict):
            return _err(
                "wrong_type",
                "Tool call function must be an object.",
                {"index": index},
                True,
            )

        if "name" not in function_obj or "arguments" not in function_obj:
            return _err(
                "missing_field",
                "Tool function requires 'name' and 'arguments'.",
                {"index": index},
                True,
            )

        if not isinstance(function_obj.get("name"), str):
            return _err(
                "wrong_type",
                "Tool function name must be string.",
                {"index": index},
                True,
            )

        if not isinstance(function_obj.get("arguments"), str):
            return _err(
                "wrong_type",
                "Tool function arguments must be stringified JSON.",
                {"index": index},
                True,
            )

    return None
