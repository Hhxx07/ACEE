"""Offline shell parser interface.

Implement rule-based or local model logic here to convert natural language into
shell commands without remote LLM calls.
"""

from __future__ import annotations

import re
import shlex
import importlib
from typing import Optional

#dynamically import
jieba = importlib.import_module("jieba") if importlib.util.find_spec("jieba") else None


SAFE_INTENTS = {
    "list_files",
    "show_cwd",
    "read_file",
    "search_files",
    "process_list",
    "network_info",
    "system_info",
    "make_dir",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()

#中英文切块
def _tokenize(text: str) -> list[str]:
    if jieba is not None:
        return [token.strip() for token in jieba.lcut(text) if token.strip()]
    # Keep Chinese and common word characters for fallback tokenization.
    return re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_./\\:-]+", text)

#根据环境选择执行的命令
def _is_windows(context: dict) -> bool:
    os_info = str(context.get("os_info", "")).lower()
    shell = str(context.get("shell", "")).lower()
    return "windows" in os_info or "powershell" in shell or "cmd" in shell

#win的转义
def _quote_target(target: str, is_windows: bool) -> str:
    if is_windows:
        escaped = target.replace('"', '""')
        return f'"{escaped}"'
    return shlex.quote(target)


def _extract_path(text: str) -> str | None:
    patterns = [
        r"(?:文件|目录|路径|folder|file)\s*[:：]?\s*([a-zA-Z]:\\[^\s,，;；]+|\./[^\s,，;；]+|/[^\s,，;；]+)",
        r"([a-zA-Z]:\\[^\s,，;；]+|\./[^\s,，;；]+|/[^\s,，;；]+)",
        r"\b([\w\-.]+\.(?:txt|md|py|json|yaml|yml|log|csv|ini|cfg))\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_extension(text: str) -> str | None:
    match = re.search(r"\.(py|txt|md|json|log|csv|yaml|yml|ini|cfg)\b", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def _extract_pid(text: str) -> str | None:
    match = re.search(r"(?:pid\s*[:：]?\s*)?(\d{2,7})\b", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _detect_intent(text: str, tokens: list[str]) -> tuple[str | None, float]:
    joined = " ".join(tokens)
    rules: list[tuple[str, tuple[str, ...], float]] = [
        ("delete", ("删除", "移除", "清空", "rm", "del", "remove"), 0.88),
        ("move", ("移动", "重命名", "mv", "move", "rename"), 0.84),
        ("make_dir", ("创建目录", "新建目录", "mkdir", "make dir"), 0.90),
        ("read_file", ("查看文件", "读取文件", "cat", "type", "open file"), 0.84),
        ("search_files", ("查找", "搜索", "find", "grep", "搜索文件"), 0.80),
        ("show_cwd", ("当前目录", "pwd", "where am i"), 0.95),
        ("list_files", ("列出", "文件列表", "ls", "dir", "list files"), 0.86),
        ("kill_process", ("结束进程", "杀进程", "kill", "taskkill"), 0.86),
        ("process_list", ("进程列表", "ps", "tasklist", "查看进程"), 0.92),
        ("network_info", ("网络", "端口", "ip", "netstat", "ifconfig"), 0.78),
        ("system_info", ("系统信息", "系统版本", "uname", "ver", "os 信息"), 0.80),
    ]

    for intent, keywords, confidence in rules:
        if any(kw in text for kw in keywords) or any(kw in joined for kw in keywords):
            return intent, confidence
    return None, 0.0


def _score_risk(
    text: str,
    intent: str,
    target: str | None,
    recursive: bool,
    forced: bool,
    has_privilege: bool,
    ambiguous: bool,
) -> tuple[float, list[str], str]:
    score = 0.05
    reasons: list[str] = []

    if intent in {"delete", "kill_process"}:
        score += 0.45
        reasons.append("destructive_action")
    elif intent in {"move"}:
        score += 0.20
        reasons.append("state_change")
    elif intent not in SAFE_INTENTS:
        score += 0.12

    if recursive:
        score += 0.20
        reasons.append("recursive_operation")

    if forced:
        score += 0.18
        reasons.append("force_flag")

    if has_privilege:
        score += 0.22
        reasons.append("privileged_context")

    if re.search(r"(?:\*|all files|全部文件|整个目录|根目录|/|c:\\windows)", text, re.IGNORECASE):
        score += 0.18
        reasons.append("broad_target")

    if re.search(r"(?:;|&&|\|\||\$\(|`)", text):
        score += 0.35
        reasons.append("command_injection_cue")

    if ambiguous:
        score += 0.25
        reasons.append("ambiguous_target")

    if target and re.search(r"(?:^/$|^\\$|^c:\\$|^~$|/etc|/usr|/bin|/var)", target, re.IGNORECASE):
        score += 0.25
        reasons.append("sensitive_path")

    score = max(0.0, min(1.0, score))
    if score >= 0.70:
        level = "high"
    elif score >= 0.35:
        level = "medium"
    else:
        level = "low"

    return score, reasons, level


def _build_command(
    intent: str,
    text: str,
    target: str | None,
    extension: str | None,
    pid: str | None,
    is_windows: bool,
    recursive: bool,
) -> str:
    if intent == "show_cwd":
        return "cd" if is_windows else "pwd"

    if intent == "list_files":
        return "dir" if is_windows else "ls -la"

    if intent == "search_files":
        if extension:
            return f"dir /s /b *.{extension}" if is_windows else f"find . -type f -name '*.{extension}'"
        return "dir /s /b" if is_windows else "find . -maxdepth 3 -type f"

    if intent == "read_file" and target:
        quoted = _quote_target(target, is_windows)
        return f"type {quoted}" if is_windows else f"cat {quoted}"

    if intent == "make_dir" and target:
        quoted = _quote_target(target, is_windows)
        return f"mkdir {quoted}" if is_windows else f"mkdir -p {quoted}"

    if intent == "move" and target and " 到 " in text:
        parts = re.split(r"\s+到\s+", text, maxsplit=1)
        destination = _extract_path(parts[-1]) if len(parts) > 1 else None
        if destination:
            src = _quote_target(target, is_windows)
            dst = _quote_target(destination, is_windows)
            return f"move {src} {dst}" if is_windows else f"mv -i {src} {dst}"

    if intent == "delete" and target:
        quoted = _quote_target(target, is_windows)
        if is_windows:
            if recursive:
                return f"powershell -Command Remove-Item -LiteralPath {quoted} -Recurse -Confirm"
            return f"del {quoted}"
        if recursive:
            return f"rm -ri {quoted}"
        return f"rm -i {quoted}"

    if intent == "process_list":
        return "tasklist" if is_windows else "ps aux"

    if intent == "kill_process" and pid:
        return f"taskkill /PID {pid}" if is_windows else f"kill {pid}"

    if intent == "network_info":
        return "netstat -ano" if is_windows else "netstat -an"

    if intent == "system_info":
        return "ver" if is_windows else "uname -a"

    return ""


def generate_command_offline(
    task_description: str,
    user_input: str,
    context: dict,
) -> Optional[dict]:
    """Generate shell command from natural language using offline logic.

    Return a dict with keys:
    - intent: run_command | ask_clarification | refuse
    - command: shell command string (empty when not run_command)
    - reason: short explanation
    - risk_level: low | medium | high
    - clarification_options: list[str] (optional)
    - allow_fallback: bool (optional, used by shell_agent in auto mode)

    This placeholder returns a structured refusal by default.
    """
    text = _normalize(f"{task_description} {user_input}")
    tokens = _tokenize(text)
    is_windows = _is_windows(context)

    intent, confidence = _detect_intent(text, tokens)
    if not intent:
        return {
            "intent": "refuse",
            "command": "",
            "reason": "Offline parser could not identify a clear intent",
            "risk_level": "medium",
            "risk_score": 0.50,
            "risk_reasons": ["unknown_intent"],
            "clarification_options": [
                "请明确你想执行的操作，例如：列出文件、查看目录、查找 .py 文件",
            ],
            "allow_fallback": True,
        }

    target = _extract_path(text)
    extension = _extract_extension(text)
    pid = _extract_pid(text)

    recursive = bool(re.search(r"(?:递归|recursive|-r\b|/s\b)", text, re.IGNORECASE))
    forced = bool(re.search(r"(?:强制|force|-f\b|/f\b)", text, re.IGNORECASE))
    has_privilege = bool(re.search(r"(?:sudo|管理员|admin|root)", text, re.IGNORECASE))

    needs_target = intent in {"read_file", "delete", "move", "make_dir"}
    ambiguous = needs_target and not target

    risk_score, risk_reasons, risk_level = _score_risk(
        text=text,
        intent=intent,
        target=target,
        recursive=recursive,
        forced=forced,
        has_privilege=has_privilege,
        ambiguous=ambiguous,
    )

    if ambiguous:
        return {
            "intent": "ask_clarification",
            "command": "",
            "reason": "缺少明确目标路径，无法安全生成命令",
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "risk_reasons": risk_reasons,
            "clarification_options": [
                "请提供完整路径，例如 ./data/log.txt",
                "仅在当前目录操作（请确认）",
                "取消该操作",
            ],
            "allow_fallback": False,
        }

    command = _build_command(
        intent=intent,
        text=text,
        target=target,
        extension=extension,
        pid=pid,
        is_windows=is_windows,
        recursive=recursive,
    )

    if not command:
        return {
            "intent": "ask_clarification",
            "command": "",
            "reason": "识别到意图但不够确定，说的再准确点",
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "risk_reasons": risk_reasons,
            "clarification_options": [
                "补充文件路径或目录路径",
                "改为查看类命令（例如列出文件）",
            ],
            "allow_fallback": confidence < 0.75,
        }

    return {
        "intent": "run_command",
        "command": command,
        "reason": "Generated by offline parser using regex + local NLP heuristics",
        "risk_level": risk_level,
        "risk_score": round(risk_score, 2),
        "risk_reasons": risk_reasons,
        "clarification_options": [],
        "allow_fallback": confidence < 0.70,
    }
