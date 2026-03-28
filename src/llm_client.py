"""Task 2.1: LLM API client with streaming support."""

import os
import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


def _get_client() -> AsyncOpenAI:
    #完成调用api的基本设置
    return AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )


MODEL = os.getenv("OPENAI_MODEL")


async def chat(messages: list[dict], temperature: float = 0.7) -> AsyncIterator[str]:
    """流式实时传送返回的信息"""
    client = _get_client()
    try:
        stream = await client.chat.completions.create(
            model=MODEL, messages=messages, temperature=temperature,
            stream=True
        )
        #一旦服务器传来信息就处理
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content #用yield直接把信息抛给前段输出
                #同时整个函数异步，可以一直保持其他地方（like ui）工作正常
    except Exception as e:
        yield f"\n[LLM Error] {e}"


async def chat_json(messages: list[dict], temperature: float = 0.3) -> dict | None:
    """Chat completion expecting JSON output. Retries once on parse failure."""
    client = _get_client()

    #在这里一共解析两次，第一次尝试失败的话（类型失败），就修正后再来一次。
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
