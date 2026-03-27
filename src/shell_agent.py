"""Task 3.1: Shell Agent — natural language to shell command with safety checks."""

import os
import platform
from . import llm_client
from .safety import check_command
from .local_nlp import try_local_conversion
from .a2a_protocol import bus, AgentMessage
from .agents_md import get_custom_rules

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
    First tries local NLP (Bonus 2), falls back to LLM if no match.
    """
    # Bonus 2: Try local conversion first (fast, no API call)
    local_result = try_local_conversion(user_input)
    if local_result is not None:
        return local_result

    ctx = _get_context()
    system_msg = SHELL_SYSTEM_PROMPT.format(**ctx)

    # Bonus 4: Inject custom rules from AGENTS.md
    custom_rules = get_custom_rules("shell_agent")
    if custom_rules:
        rules_text = "\n".join(f"- {r}" for r in custom_rules)
        system_msg += f"\n\n## Custom Rules (from AGENTS.md)\n{rules_text}"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": f"Original user request: {user_input}\n\nTask from orchestrator: {task_description}"},
    ]

    result = await llm_client.chat_json(messages)
    if result is None:
        return build_error_response("Failed to generate command (LLM parse error)")
    
    intent = result.get("intent","refuse").lower()
    """ # 原先的代码没有处理ask_clarification


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

    """
    if intent == "ask_clarification":
         # 显式提取 clarification_options，如果 LLM 没有提供则默认为空列表
        clarification_options = result.get("clarification_options", [])
        
        # 构建返回结果
        clarification_result = {
            "intent": "ask_clarification",
            "command": "",  # 澄清时命令为空
            "reason": result.get("reason", "需要澄清用户意图"),
            "risk_level": "low",  # 澄清本身是低风险的
            "clarification_options": clarification_options,  # 确保返回选项
            "safety_check": {"level": "safe", "reasons": ["Awaiting user clarification"]}
        }
        return clarification_result

    elif intent == "refuse":
        # 如果是拒绝，直接返回
        result["safety_check"] = {"level": "deny", "reasons": [result.get("reason", "Unknown reason")]}
        return result

    elif intent == "run_command":
        # 只有在明确要执行命令时，才进行安全检查
        command = result.get("command", "").strip()
        if not command:
            return build_error_response("Empty command")
        
        safety = check_command(command)
        result["safety_check"] = safety

        # 安全检查拦截：这里可以决定是拒绝还是降级
        if safety["level"] == "deny":
            result["intent"] = "refuse"
            result["reason"] = f"BLOCKED by safety engine: {'; '.join(safety['reasons'])}"
            result["risk_level"] = "high"
        # 如果只是警告，可以保留 run_command 意图，但提示用户
        elif safety["level"] == "warn" and result.get("risk_level") == "low":
            result["risk_level"] = "medium"

        return result

    else:
        # 兜底逻辑
        return build_error_response("Invalid intent from LLM")
    return result

def build_error_response(reason):
    """辅助函数：构建错误返回"""
    return {
        "intent": "refuse",
        "command": "",
        "reason": reason,
        "risk_level": "high",
        "safety_check": {"level": "deny", "reasons": [reason]},
    }

# --- A2A Protocol integration (Bonus 3) ---

async def _a2a_generate(message: AgentMessage) -> dict:
    """A2A handler: generate command via the bus."""
    task = message.payload.get("task_description", "")
    user_input = message.payload.get("user_input", "")
    return await generate_command(task, user_input)


def register_on_bus():
    """Register shell agent on the A2A message bus."""
    bus.register_agent("shell_agent", {
        "generate_command": _a2a_generate,
    })
