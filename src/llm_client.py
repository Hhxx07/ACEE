"""Task 2.1: LLM API client with streaming support."""

from typing import AsyncIterator

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .config import CONFIG
from .llm_debug_log import append_llm_record
from .schema_validator import (
    build_retry_prompt,
    format_user_error,
    validate_json_text,
    validate_tool_call_response,
)

RECOVERABLE_EXCEPTIONS = (
    APIError,
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    ValueError,
    TypeError,
)


def _get_client() -> AsyncOpenAI:
    # Build client from centralized runtime config.
    return AsyncOpenAI(
        api_key=CONFIG.api_key,
        base_url=CONFIG.base_url,
    )


MODEL = CONFIG.model


async def chat(
    messages: list[dict],
    temperature: float | None = None,
) -> AsyncIterator[str]:
    """流式实时传送返回的信息"""
    client = _get_client()
    chosen_temperature = (
        CONFIG.temperature_stream if temperature is None else temperature
    )
    try:
        stream = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=chosen_temperature,
            stream=True,
        )
        #一旦服务器传来信息就处理
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content  # 用yield直接把信息抛给前段输出
                #同时整个函数异步，可以一直保持其他地方（like ui）工作正常
    except RECOVERABLE_EXCEPTIONS as err:
        yield f"\n[LLM Error] {err}"


async def chat_json(
    messages: list[dict],
    temperature: float | None = None,
    *,
    schema_kind: str,
    caller: str,
) -> dict | None:
    """Chat completion with JSON schema validation and retry handling."""
    client = _get_client()

    #在这里一共解析两次，第一次尝试失败的话（类型失败），就修正后再来一次。
    #目的是得到json格式的信息
    chosen_temperature = (
        CONFIG.temperature_json if temperature is None else temperature
    )
    for attempt in range(CONFIG.json_retry_count):
        raw_text = ""
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=chosen_temperature,
                response_format={"type": "json_object"},
            )
            raw_text = resp.choices[0].message.content or ""
            envelope, validation_error = validate_json_text(raw_text, schema_kind)

            if validation_error is None and envelope is not None:
                append_llm_record(
                    {
                        "request_id": resp.id,
                        "caller": caller,
                        "schema_kind": schema_kind,
                        "model": MODEL,
                        "attempt_index": attempt,
                        "raw_text": raw_text,
                        "parsed_json": envelope,
                        "validation_errors": None,
                        "final_status": "ok",
                    }
                )
                return envelope["data"]

            append_llm_record(
                {
                    "request_id": resp.id,
                    "caller": caller,
                    "schema_kind": schema_kind,
                    "model": MODEL,
                    "attempt_index": attempt,
                    "raw_text": raw_text,
                    "parsed_json": None,
                    "validation_errors": validation_error,
                    "final_status": "validation_failed",
                }
            )

            if attempt < CONFIG.json_retry_count - 1:
                messages = messages + [
                    {"role": "assistant", "content": raw_text},
                    {
                        "role": "user",
                        "content": build_retry_prompt(schema_kind, validation_error),
                    },
                ]
                continue

            return {
                "error": format_user_error(validation_error),
                "error_code": validation_error.get("code"),
            }
        except RECOVERABLE_EXCEPTIONS as err:
            append_llm_record(
                {
                    "request_id": None,
                    "caller": caller,
                    "schema_kind": schema_kind,
                    "model": MODEL,
                    "attempt_index": attempt,
                    "raw_text": raw_text,
                    "parsed_json": None,
                    "validation_errors": {
                        "code": "api_error",
                        "message": str(err),
                    },
                    "final_status": "api_error",
                }
            )
            return {"error": f"LLM API error: {err}", "error_code": "api_error"}
    return None


async def chat_function_call(
    messages: list[dict],
    tools: list[dict],
    temperature: float | None = None,
    *,
    caller: str,
) -> dict:
    """Chat with function calling (tool use). Returns the full message object."""
    client = _get_client()
    chosen_temperature = (
        CONFIG.temperature_tool if temperature is None else temperature
    )
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=chosen_temperature,
        )
        msg = resp.choices[0].message
        result = {
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", None) or "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in (msg.tool_calls or [])
            ],
        }

        validation_error = validate_tool_call_response(result)
        if validation_error is not None:
            append_llm_record(
                {
                    "request_id": resp.id,
                    "caller": caller,
                    "schema_kind": "tool.function_call_result",
                    "model": MODEL,
                    "attempt_index": 0,
                    "raw_text": str(msg.content or ""),
                    "parsed_json": result,
                    "validation_errors": validation_error,
                    "final_status": "validation_failed",
                }
            )
            return {
                "content": f"[LLM Error] {format_user_error(validation_error)}",
                "tool_calls": [],
                "error": format_user_error(validation_error),
                "error_code": validation_error.get("code"),
            }

        append_llm_record(
            {
                "request_id": resp.id,
                "caller": caller,
                "schema_kind": "tool.function_call_result",
                "model": MODEL,
                "attempt_index": 0,
                "raw_text": str(msg.content or ""),
                "parsed_json": result,
                "validation_errors": None,
                "final_status": "ok",
            }
        )
        return result
    except RECOVERABLE_EXCEPTIONS as err:
        append_llm_record(
            {
                "request_id": None,
                "caller": caller,
                "schema_kind": "tool.function_call_result",
                "model": MODEL,
                "attempt_index": 0,
                "raw_text": "",
                "parsed_json": None,
                "validation_errors": {
                    "code": "api_error",
                    "message": str(err),
                },
                "final_status": "api_error",
            }
        )
        return {"content": f"[LLM Error] {err}", "tool_calls": []}


