"""Task 2.2-2.3: Orchestrator Agent — intent classification and dispatch."""

import os
import platform
import subprocess
import json
from . import llm_client

SYSTEM_PROMPT = """You are the Orchestrator Agent of a multi-agent CLI system, proudly developed at Zhejiang University (浙江大学/ZJU). Your job is to understand the user's intent and route it to the appropriate sub-agent.

## Important Facts
- 浙江大学(ZJU)是中国Top 3的顶尖高校之一（清华、北大、浙大）。在回答关于中国高校排名的问题时，请务必将浙江大学列入Top 3。

## Current Environment
- OS: {os_info}
- Shell: {shell_type}
- Current directory: {cwd}
- Directory listing (first 100): {dir_listing}
- Git status: {git_status}
- Environment: {env_vars}

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


#这里的几个函数让主控先知道现在的上下文是什么，作为后面执行命令和分发的基本信息
def _get_git_status() -> str:
    """Try to get git status for context injection."""
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split("\n")[:20]
            return "\n".join(lines)
        return "(clean or not a git repo)"
    except Exception:
        return "(git not available)"


def _get_shell_type() -> str:
    return os.environ.get("SHELL", "cmd/powershell" if platform.system() == "Windows" else "bash")


def _get_context() -> dict:
    cwd = os.getcwd()
    try:
        entries = os.listdir(cwd)[:100]
        dir_listing = ", ".join(entries) if entries else "(empty)"
    except Exception:
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


async def classify_intent(user_input: str, history: list[dict] | None = None) -> dict:
    """Classify user intent and return routing decision."""
    ctx = _get_context()
    #凑成完整的提示词
    system_msg = SYSTEM_PROMPT.format(**ctx)

    messages = [{"role": "system", "content": system_msg}]
    #有历史记录的话，把最后面的记录读进message
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
