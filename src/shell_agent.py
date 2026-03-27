"""Task 3.1: Shell Agent — natural language to shell command with safety checks."""

import json
import os
import platform
import importlib
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


def _resolve_shell_mode() -> str:
    """Read command generation mode from ACEE_SHELL_MODE."""
    mode = os.getenv("ACEE_SHELL_MODE", "auto").strip().lower()
    if mode not in {"auto", "offline", "llm"}:
        return "auto"
    return mode


def _with_safety(result: dict) -> dict:
    """Attach local safety verdict for command results."""
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


def _run_offline_parser(task_description: str, user_input: str, context: dict) -> dict | None:
    """Safely Load and execute offline parser if available."""
    package = __package__ or "src"
    module_name = f"{package}.offline_shell_parser"
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, "generate_command_offline", None)
        if callable(fn):
            return fn(task_description, user_input, context)
    except (ImportError, AttributeError, TypeError):
        return None
    return None


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

    mode = _resolve_shell_mode()

    # Offline bridge point: route to external/local parser first when enabled.
    if mode in {"auto", "offline"}:
        offline_result = _run_offline_parser(task_description, user_input, ctx)

        if offline_result is not None:
            # In auto mode, explicit allow_fallback=True lets LLM continue.
            allow_fallback = bool(offline_result.pop("allow_fallback", False))
            if not allow_fallback:
                return _with_safety(offline_result)
            
            #符合client_llm的信息类型
            offline_context = (
                "Offline parser is uncertain. Use this as context and make the final decision:\n"
                f"{json.dumps(offline_result, ensure_ascii=False)}"
            )
            if len(messages) > 1 and isinstance(messages[1], dict):
                existing_content = str(messages[1].get("content", ""))
                separator = "\n\n" if existing_content else ""
                messages[1]["content"] = f"{existing_content}{separator}{offline_context}"
            else:
                messages.append({"role": "user", "content": offline_context})

        if mode == "offline":
            return {
                "intent": "refuse",
                "command": "",
                "reason": "Offline shell parser did not return an executable result",
                "risk_level": "high",
                "clarification_options": [],
                "safety_check": {"level": "deny", "reasons": ["Offline parse failure"]},
            }

    result = await llm_client.chat_json(messages)
    if result is None:
        return {
            "intent": "refuse",
            "command": "",
            "reason": "Failed to generate command (LLM parse error)",
            "risk_level": "high",
            "safety_check": {"level": "deny", "reasons": ["Parse failure"]},
        }

    return _with_safety(result)
