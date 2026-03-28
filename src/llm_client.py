"""Task 2.1: LLM API client with streaming support."""

import json
from typing import AsyncIterator

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .config import CONFIG

load_dotenv()

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
) -> dict | None:
    """Chat completion expecting JSON output. Retries once on parse failure."""
    client = _get_client()

    #在这里一共解析两次，第一次尝试失败的话（类型失败），就修正后再来一次。
    #目的是得到json格式的信息
    chosen_temperature = (
        CONFIG.temperature_json if temperature is None else temperature
    )
    for attempt in range(CONFIG.json_retry_count):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=chosen_temperature,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or ""
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt < CONFIG.json_retry_count - 1:
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {
                        "role": "user",
                        "content": (
                            "Your response was not valid JSON. "
                            "Please output ONLY valid JSON."
                        ),
                    },
                ]
                continue
            return None
        except RECOVERABLE_EXCEPTIONS as err:
            return {"error": str(err)}
    return None


async def chat_function_call(
    messages: list[dict],
    tools: list[dict],
    temperature: float | None = None,
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
        return {
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
    except RECOVERABLE_EXCEPTIONS as err:
        return {"content": f"[LLM Error] {err}", "tool_calls": []}


