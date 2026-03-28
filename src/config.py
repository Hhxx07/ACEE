"""Centralized runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    api_key: str | None
    base_url: str | None
    model: str | None
    temperature_stream: float
    temperature_json: float
    temperature_tool: float
    json_retry_count: int


def _get_float(
    key: str,
    default: float,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    raw = os.getenv(key)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = default

    if min_value is not None and value < min_value:
        return min_value
    if max_value is not None and value > max_value:
        return max_value
    return value


def _get_int(
    key: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    raw = os.getenv(key)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default

    if min_value is not None and value < min_value:
        return min_value
    if max_value is not None and value > max_value:
        return max_value
    return value


def _build_llm_config() -> LLMConfig:
    return LLMConfig(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        model=os.getenv("OPENAI_MODEL"),
        temperature_stream=_get_float(
            "OPENAI_TEMPERATURE_STREAM",
            0.7,
            min_value=0.0,
            max_value=2.0,
        ),
        temperature_json=_get_float(
            "OPENAI_TEMPERATURE_JSON",
            0.3,
            min_value=0.0,
            max_value=2.0,
        ),
        temperature_tool=_get_float(
            "OPENAI_TEMPERATURE_TOOL",
            0.3,
            min_value=0.0,
            max_value=2.0,
        ),
        json_retry_count=_get_int(
            "OPENAI_JSON_RETRY_COUNT",
            2,
            min_value=1,
        ),
    )


CONFIG = _build_llm_config()
