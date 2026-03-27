"""Task 3.1: Shell Agent — natural language to shell command with safety checks."""

import os
import platform
from . import llm_client
from .safety import check_command

SHELL_SYSTEM_PROMPT = """You are the Shell Agent. Your job is to convert natural language requests into safe, executable shell commands.

## Environment
- OS: {os_info}
- Shell: {shell}
- Current directory: {cwd}
- Directory listing: {dir_listing}

## Instructions
Given the user's request and context from the Orchestrator Agent, generate a shell command.
Respond with ONLY a JSON object:
{{
  "intent": "run_command" | "ask_clarification" | "refuse",
  "command": "the shell command to execute (empty if not run_command)",
  "reason": "Brief explanation of what this command does",
  "risk_level": "low" | "medium" | "high",
  "clarification_options": ["option1", "option2"]
}}

## Safety Rules
- NEVER generate commands that could destroy the system (rm -rf /, mkfs, dd, etc.)
- Mark destructive commands (rm, mv, chmod) as medium or high risk
- If the request is ambiguous (e.g., "delete that file"), use ask_clarification with options
- If the request is inherently dangerous, use refuse
- Prefer safe alternatives (e.g., use 'ls' instead of 'find / ...')

Respond with ONLY the JSON object."""


def _get_context() -> dict:
    cwd = os.getcwd()
    try:
        entries = os.listdir(cwd)[:100]
        dir_listing = ", ".join(entries) if entries else "(empty)"
    except Exception:
        dir_listing = "(cannot read)"

    shell = "bash" if platform.system() != "Windows" else "cmd/powershell"
    return {
        "os_info": f"{platform.system()} {platform.release()}",
        "shell": shell,
        "cwd": cwd,
        "dir_listing": dir_listing,
    }


async def generate_command(task_description: str, user_input: str) -> dict:
    """Generate a shell command from natural language.

    Returns dict with: intent, command, reason, risk_level, safety_check
    """
    ctx = _get_context()
    system_msg = SHELL_SYSTEM_PROMPT.format(**ctx)

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Original user request: {user_input}\n\nTask from orchestrator: {task_description}"},
    ]

    result = await llm_client.chat_json(messages)
    if result is None:
        return {
            "intent": "refuse",
            "command": "",
            "reason": "Failed to generate command (LLM parse error)",
            "risk_level": "high",
            "safety_check": {"level": "deny", "reasons": ["Parse failure"]},
        }

    # Double-check with local safety engine
    command = result.get("command", "")
    if command:
        safety = check_command(command)
        result["safety_check"] = safety

        # Override risk level if local engine disagrees
        if safety["level"] == "deny":
            result["risk_level"] = "high"
            result["intent"] = "refuse"
            result["reason"] = f"BLOCKED by safety engine: {'; '.join(safety['reasons'])}"
        elif safety["level"] == "warn" and result.get("risk_level") == "low":
            result["risk_level"] = "medium"
    else:
        result["safety_check"] = {"level": "safe", "reasons": []}

    return result
