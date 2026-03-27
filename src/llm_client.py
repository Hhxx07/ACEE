"""Task 2.1: LLM API client with streaming support."""

import os
import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY", ""),
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


async def chat(messages: list[dict], temperature: float = 0.7) -> str:
    """Non-streaming chat completion."""
    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM Error] {e}"


async def chat_stream(messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]:
    """Streaming chat completion, yields token chunks."""
    client = _get_client()
    try:
        stream = await client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature, stream=True
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
    except Exception as e:
        yield f"\n[LLM Error] {e}"


async def chat_json(messages: list[dict], temperature: float = 0.3) -> dict | None:
    """Chat completion expecting JSON output. Retries once on parse failure."""
    client = _get_client()
    for attempt in range(2):
        try:
            resp = await client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or ""
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt == 0:
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "Your response was not valid JSON. Please output ONLY valid JSON."},
                ]
                continue
            return None
        except Exception as e:
            return {"error": str(e)}
    return None


async def chat_function_call(messages: list[dict], tools: list[dict], temperature: float = 0.3) -> dict:
    """Chat with function calling (tool use). Returns the full message object."""
    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
        )
        msg = resp.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": getattr(tc, "type", None) or "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in (msg.tool_calls or [])
            ],
        }
    except Exception as e:
        return {"content": f"[LLM Error] {e}", "tool_calls": []}
