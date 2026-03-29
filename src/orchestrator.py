"""Task 2.2-2.3: Orchestrator Agent — intent classification and dispatch."""

import os
import platform
import subprocess
import importlib
from datetime import datetime, timezone

from . import llm_client
from .schema_protocol import SCHEMA_KIND_ORCHESTRATOR

SYSTEM_PROMPT = """You are the Orchestrator Agent of a multi-agent CLI system. Your job is to understand the user's intent and route it to the appropriate sub-agent.


## Current Environment
- OS: {os_info}
- Shell: {shell_type}
- Current directory: {cwd}
- Context signals: {context_signals}

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


MAX_CONTEXT_FIELD_CHARS = 320


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


def _sanitize_context_value(value: str, max_chars: int = MAX_CONTEXT_FIELD_CHARS) -> str:
    """Normalize context fields to keep prompts stable and concise."""
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        return "(none)"
    if len(cleaned) > max_chars:
        return f"{cleaned[:max_chars]}..."
    return cleaned


def _derive_repo_signal(entries: list[str], git_status_text: str) -> str:
    git_repo = "yes" if git_status_text != "(clean or not a git repo)" else "no"
    dirty_count = 0
    if git_status_text not in {"(clean or not a git repo)", "(git not available)"}:
        dirty_count = len([line for line in git_status_text.split("\n") if line.strip()])

    marker_map = {
        "python": ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
        "node": ["package.json", "pnpm-lock.yaml", "yarn.lock"],
        "java": ["pom.xml", "build.gradle"],
        "go": ["go.mod"],
        "rust": ["Cargo.toml"],
    }
    lower_entries = {name.lower() for name in entries}
    tags: list[str] = []
    for tag, markers in marker_map.items():
        if any(marker.lower() in lower_entries for marker in markers):
            tags.append(tag)
    if not tags:
        tags.append("unknown")

    return f"git_repo={git_repo}; dirty_files={dirty_count}; repo_tags={','.join(tags)}"


def _derive_exec_signal(entries: list[str]) -> str:
    executable_ext = (".py", ".sh", ".ps1", ".bat", ".cmd", ".exe")
    exec_candidates = [name for name in entries if name.lower().endswith(executable_ext)]
    preview = ", ".join(exec_candidates[:8]) if exec_candidates else "(none)"
    return f"exec_candidates={len(exec_candidates)}; examples={preview}"


def _derive_language_signal(entries: list[str]) -> str:
    extension_counts: dict[str, int] = {}
    for name in entries:
        if "." not in name:
            continue
        ext = f".{name.rsplit('.', 1)[-1].lower()}"
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
    if not extension_counts:
        return "primary_extension=(none); top_extensions=(none)"

    sorted_ext = sorted(extension_counts.items(), key=lambda item: item[1], reverse=True)
    top_ext = sorted_ext[0][0]
    top_preview = ", ".join(f"{ext}:{count}" for ext, count in sorted_ext[:5])
    return f"primary_extension={top_ext}; top_extensions={top_preview}"


def _derive_directory_risk(cwd: str) -> str:
    """Mark potentially risky working directories for destructive shell intents."""
    norm = os.path.normpath(cwd)
    _, tail = os.path.splitdrive(norm)
    is_root = tail in {"\\", "/", ""}
    risky = is_root or norm.lower().startswith(("c:\\windows", "c:\\program files"))
    return "high" if risky else "normal"


def _build_context_signals(cwd: str, entries: list[str], git_status_text: str) -> str:
    signals = [
        _derive_repo_signal(entries, git_status_text),
        _derive_exec_signal(entries),
        _derive_language_signal(entries),
        f"directory_risk={_derive_directory_risk(cwd)}",
        f"entry_count={len(entries)}",
    ]
    return " | ".join(signals)


def _get_context() -> dict:
    cwd = os.getcwd()
    entries: list[str] = []
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
    context_signals = _build_context_signals(cwd, entries, git_status)

    return {
        "os_info": _sanitize_context_value(f"{platform.system()} {platform.release()}"),
        "cwd": _sanitize_context_value(cwd),
        "dir_listing": _sanitize_context_value(dir_listing),
        "git_status": _sanitize_context_value(git_status),
        "shell_type": _sanitize_context_value(_get_shell_type()),
        "env_vars": _sanitize_context_value(env_str),
        "context_signals": _sanitize_context_value(context_signals, max_chars=640),
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
        "context_signals": "(not injected)",
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


def _resolve_orch_offline_first() -> bool:
    """Control offline pre-classification via ACEE_ORCH_OFFLINE_FIRST."""
    raw = os.getenv("ACEE_ORCH_OFFLINE_FIRST", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _orchestrator_context_for_offline(use_context: bool) -> dict:
    """Build context shape expected by offline_shell_parser."""
    if not use_context:
        return {
            "os_info": "(not injected)",
            "shell": "(not injected)",
            "cwd": "(not injected)",
            "dir_listing": "(not injected)",
        }

    ctx = _get_context()
    return {
        "os_info": ctx.get("os_info", ""),
        "shell": ctx.get("shell_type", ""),
        "cwd": ctx.get("cwd", ""),
        "dir_listing": ctx.get("dir_listing", ""),
    }

#重新包装离线解析器的结果，决定是不是要走api
def _map_offline_to_classification(user_input: str, offline_result: dict) -> dict | None:
    """Map offline parser output into orchestrator classification contract."""
    intent = str(offline_result.get("intent", "")).strip().lower()
    command = str(offline_result.get("command", "")).strip()
    reason = str(offline_result.get("reason", "Offline parser decision")).strip()
    allow_fallback = bool(offline_result.get("allow_fallback", False))

    if allow_fallback:
        return None

    if intent == "run_command" and command:
        return {
            "intent": "shell_agent",
            "reasoning": f"Offline pre-classifier hit: {reason}",
            "confidence": 0.93,
            "message": None,
            "task_description": user_input,
        }

    if intent == "ask_clarification":
        options = offline_result.get("clarification_options", [])
        if isinstance(options, list) and options:
            option_text = " | ".join(str(item) for item in options[:3])
            message = f"{reason}\nOptions: {option_text}"
        else:
            message = reason
        return {
            "intent": "clarification",
            "reasoning": "Offline pre-classifier needs clarification",
            "confidence": 0.85,
            "message": message,
            "task_description": "",
        }

    if intent == "refuse":
        return {
            "intent": "clarification",
            "reasoning": "Offline pre-classifier refused",
            "confidence": 0.82,
            "message": reason,
            "task_description": "",
        }

    return None


def _classify_intent_offline(user_input: str, context: dict) -> dict | None:
    """Try local/offline shell intent pre-classification before any API call."""
    package = __package__ or "src"
    module_name = f"{package}.offline_shell_parser"

    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, "generate_command_offline", None)
        if not callable(fn):
            return None

        offline_result = fn(user_input, user_input, context)
        if not isinstance(offline_result, dict):
            return None

        return _map_offline_to_classification(user_input, offline_result)
    except (ImportError, AttributeError, TypeError):
        return None


async def classify_intent(
    user_input: str,
    history: list[dict] | None = None,
    *,
    use_context: bool = True,
    startup_context: str = "",
) -> dict:
    """Classify user intent and return routing decision."""
    context_mode = "with_context" if use_context else "without_context"

    #在尝试调用api之前先尝试直接离线生成命令
    if _resolve_orch_offline_first():
        offline_ctx = _orchestrator_context_for_offline(use_context=use_context)
        offline_classification = _classify_intent_offline(user_input, offline_ctx)
        if offline_classification is not None:
            offline_classification.setdefault("context_mode", context_mode)
            offline_classification.setdefault("offline_hit", True)
            return offline_classification

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
            "context_mode": context_mode,
            "offline_hit": False,
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
            "context_mode": context_mode,
            "offline_hit": False,
        }

    if isinstance(result, dict):
        result.setdefault("context_mode", context_mode)
        result.setdefault("offline_hit", False)

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
