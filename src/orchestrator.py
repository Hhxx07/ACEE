"""Task 2.2-2.3: Orchestrator Agent — intent classification and dispatch."""

import os
import platform
import json
from . import llm_client

SYSTEM_PROMPT = """You are the Orchestrator Agent of a multi-agent CLI system. Your job is to understand the user's intent and route it to the appropriate sub-agent.

## Current Environment
- OS: {os_info}
- Current directory: {cwd}
- Directory listing (first 100): {dir_listing}

## Available Agents
1. **shell_agent** — Execute system/shell commands (file operations, process management, system admin, etc.)
2. **tool_agent** — Use built-in tools for structured tasks (read/write files, get system info, fetch URLs, search files, etc.)
3. **direct_answer** — Answer questions directly without executing anything (general knowledge, time, greetings, etc.)
4. **clarification** — When the user's intent is ambiguous and you need more information.

## Instructions
Analyze the user's input and respond with a JSON object:
{{
  "intent": "shell_agent" | "tool_agent" | "direct_answer" | "clarification",
  "reasoning": "Brief explanation of why you chose this intent",
  "confidence": 0.0 to 1.0,
  "message": "Your direct answer (only if intent is direct_answer or clarification)",
  "task_description": "Clear description of what the sub-agent should do (for shell_agent/tool_agent)"
}}

## Routing Guidelines
- File listing, process management, networking commands, package management → shell_agent
- Reading file contents, writing files, checking if files exist, getting system info, fetching URLs → tool_agent
- Questions about general knowledge, greetings, time, "what is X" → direct_answer
- Ambiguous requests like "delete that file" (which file?) → clarification
- When in doubt between shell_agent and tool_agent, prefer tool_agent for read-only operations

Respond with ONLY the JSON object, no other text."""


def _get_context() -> dict:
    cwd = os.getcwd()
    try:
        entries = os.listdir(cwd)[:100]
        dir_listing = ", ".join(entries) if entries else "(empty)"
    except Exception:
        dir_listing = "(cannot read)"
    return {
        "os_info": f"{platform.system()} {platform.release()}",
        "cwd": cwd,
        "dir_listing": dir_listing,
    }


async def classify_intent(user_input: str, history: list[dict] | None = None) -> dict:
    """Classify user intent and return routing decision."""
    ctx = _get_context()
    system_msg = SYSTEM_PROMPT.format(**ctx)

    messages = [{"role": "system", "content": system_msg}]
    if history:
        messages.extend(history[-6:])  # Last 3 exchanges for context
    messages.append({"role": "user", "content": user_input})

    result = await llm_client.chat_json(messages)
    if result is None:
        return {
            "intent": "direct_answer",
            "reasoning": "Failed to parse LLM response",
            "confidence": 0.0,
            "message": "Sorry, I had trouble understanding. Could you rephrase?",
        }
    return result
