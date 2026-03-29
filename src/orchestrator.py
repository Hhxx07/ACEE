"""Task 2.2-2.3: Orchestrator Agent — intent classification and dispatch."""

import os
import platform
import subprocess
from datetime import datetime, timezone

from . import llm_client
from .schema_protocol import SCHEMA_KIND_ORCHESTRATOR

SYSTEM_PROMPT = """You are the Orchestrator Agent of a multi-agent CLI system. Your job is to understand the user's intent and route it to the appropriate sub-agent.


## Current Environment
- OS: {os_info}
- Shell: {shell_type}
- Current directory: {cwd}
- Directory listing (first 100): {dir_listing}
- Git status: {git_status}
- Environment: {env_vars}

## Startup Memory Snapshot
{startup_memory}

## Available Agents
1. **shell_agent** — Execute system/shell commands (file operations, process management, system admin, etc.)
2. **tool_agent** — Use built-in tools for structured tasks (read/write files, get system info, fetch URLs, search files, etc.)
3. **direct_answer** — Answer questions directly without executing anything (general knowledge, time, greetings, etc.)
4. **clarification** — When the user's intent is ambiguous and you need more information.

## Instructions
Analyze the user's input and respond with a JSON object using this envelope:
{{
    "ok": true,
    "kind": "orchestrator.classification",
    "data": {{
        "intent": "shell_agent" | "tool_agent" | "direct_answer" | "clarification",
        "reasoning": "Brief explanation of why you chose this intent",
        "confidence": 0.0 to 1.0,
        "message": "Your direct answer (only if intent is direct_answer or clarification)",
        "task_description": "Clear description of what the sub-agent should do (for shell_agent/tool_agent)"
    }},
    "error": null,
    "meta": {{}}
}}

## Routing Guidelines
- File listing, process management, networking commands, package management → shell_agent
- Reading file contents, writing files, checking if files exist, getting system info, fetching URLs → tool_agent
- Questions about general knowledge, greetings, time, "what is X" → direct_answer
- Ambiguous requests like "delete that file" (which file?) → clarification
- When in doubt between shell_agent and tool_agent, prefer tool_agent for read-only operations

Respond with ONLY the JSON object, no other text."""


#这里的几个函数让主控先知道现在的上下文是什么，作为后面执行命令和分发的基本信息
def _get_git_status() -> str:
    """Try to get git status for context injection."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")[:20]
            return "\n".join(lines)
        return "(clean or not a git repo)"
    except (OSError, subprocess.SubprocessError, TimeoutError):
        return "(git not available)"


def _get_shell_type() -> str:
    return os.environ.get("SHELL", "cmd/powershell" if platform.system() == "Windows" else "bash")


def _get_context() -> dict:
    cwd = os.getcwd()
    try:
        entries = os.listdir(cwd)[:100]
        dir_listing = ", ".join(entries) if entries else "(empty)"
    except OSError:
        dir_listing = "(cannot read)"

    git_status = _get_git_status()

    # 把环境变量中安全的内容放到context里面
    safe_env_keys = ["PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV"]
    env_vars = {k: os.environ.get(k, "") for k in safe_env_keys if os.environ.get(k)}
    env_str = ", ".join(f"{k}={v}" for k, v in list(env_vars.items())[:10]) or "(none)"

    return {
        "os_info": f"{platform.system()} {platform.release()}",
        "cwd": cwd,
        "dir_listing": dir_listing,
        "git_status": git_status,
        "shell_type": _get_shell_type(),
        "env_vars": env_str,
    }


def _empty_context() -> dict:
    """Context placeholders when environment injection is disabled."""
    return {
        "os_info": "(not injected)",
        "cwd": "(not injected)",
        "dir_listing": "(not injected)",
        "git_status": "(not injected)",
        "shell_type": "(not injected)",
        "env_vars": "(not injected)",
        "startup_memory": "(none)",
    }


def _sanitize_startup_memory(startup_context: str, max_chars: int = 1200) -> str:
    cleaned = " ".join(startup_context.split())
    if not cleaned:
        return "(none)"
    return cleaned[:max_chars]


def _build_system_prompt(use_context: bool, startup_context: str = "") -> str:
    """Build orchestrator prompt with optional environment context injection."""
    ctx = _get_context() if use_context else _empty_context()
    ctx["startup_memory"] = _sanitize_startup_memory(startup_context)
    return SYSTEM_PROMPT.format(**ctx)


async def classify_intent(
    user_input: str,
    history: list[dict] | None = None,
    *,
    use_context: bool = True,
    startup_context: str = "",
) -> dict:
    """Classify user intent and return routing decision."""
    #凑成完整的提示词
    system_msg = _build_system_prompt(use_context=use_context, startup_context=startup_context)

    messages = [{"role": "system", "content": system_msg}]
    #有历史记录的话，把最后面的记录读进message
    if history:
        messages.extend(history[-6:])  # Last 3 exchanges for context
    messages.append({"role": "user", "content": user_input})

    result = await llm_client.chat_json(
        messages,
        schema_kind=SCHEMA_KIND_ORCHESTRATOR,
        caller="orchestrator",
    )
    if result is None:
        return {
            "intent": "direct_answer",
            "reasoning": "Failed to parse LLM response",
            "confidence": 0.0,
            "message": "Sorry, I had trouble understanding. Could you rephrase?",
        }

    if isinstance(result, dict) and result.get("error"):
        reason = str(result.get("error"))
        return {
            "intent": "clarification",
            "reasoning": f"Schema validation failed: {reason}",
            "confidence": 0.0,
            "message": "I could not validate the structured response. Please try again with clearer wording.",
            "task_description": "",
            "schema_error": True,
            "error_code": result.get("error_code", "unknown_error"),
        }

    return result


def _build_ab_diff(with_context: dict, without_context: dict) -> dict:
    """Create a compact field-level difference summary for A/B comparison."""
    fields = ["intent", "confidence", "reasoning", "message", "task_description"]
    diff: dict = {}
    for field in fields:
        a_value = with_context.get(field)
        b_value = without_context.get(field)
        if a_value != b_value:
            diff[field] = {
                "with_context": a_value,
                "without_context": b_value,
            }
    return {
        "changed": bool(diff),
        "changed_fields": sorted(diff.keys()),
        "details": diff,
    }


async def classify_intent_compare_context(
    user_input: str,
    history: list[dict] | None = None,
) -> dict:
    """Run two passes (with/without context injection) for side-by-side comparison."""
    with_context = await classify_intent(user_input, history=history, use_context=True)
    without_context = await classify_intent(user_input, history=history, use_context=False)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": llm_client.MODEL,
        "user_input": user_input,
        "with_context": with_context,
        "without_context": without_context,
        "diff": _build_ab_diff(with_context=with_context, without_context=without_context),
    }
