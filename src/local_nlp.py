"""Bonus 2: Local natural language conversion — keyword-based NL→command without LLM.

Handles common patterns locally to reduce latency and API costs.
Falls back to LLM for complex/ambiguous requests.
"""

import os
import re
import platform

# Pattern rules: (regex_pattern, handler_function)
# Each handler returns (command, reason) or None if no match.

def _get_shell():
    return "bash" if platform.system() != "Windows" else "cmd"


def _try_list_files(text: str) -> tuple[str, str] | None:
    """Match: list files, show files, ls, dir, show directory, etc."""
    patterns = [
        r"(?:list|show|display|see)\s+(?:all\s+)?(?:files|directory|dir|folder|contents)",
        r"(?:what(?:'s| is| are)\s+in\s+(?:this|the|current)\s+(?:directory|folder|dir))",
        r"^(?:ls|dir)\b",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            # Check for specific path
            path_match = re.search(r"(?:in|of|for)\s+[\"']?([^\s\"']+)[\"']?", text)
            path = path_match.group(1) if path_match else "."
            if platform.system() == "Windows":
                return f"dir {path}", f"List contents of {path}"
            return f"ls -la {path}", f"List contents of {path}"
    return None


def _try_find_files(text: str) -> tuple[str, str] | None:
    """Match: find files by extension or name pattern."""
    # "find all python files", "find *.py files", "search for .txt files"
    m = re.search(
        r"(?:find|search|look for|locate)\s+(?:all\s+)?(?:(\w+)\s+files|files?\s+(?:named|called|with)\s+[\"']?([^\s\"']+))",
        text, re.IGNORECASE,
    )
    if m:
        ext_or_lang = m.group(1) or m.group(2)
        lang_map = {
            "python": "*.py", "py": "*.py",
            "javascript": "*.js", "js": "*.js",
            "typescript": "*.ts", "ts": "*.ts",
            "java": "*.java", "c": "*.c", "cpp": "*.cpp",
            "rust": "*.rs", "go": "*.go",
            "markdown": "*.md", "md": "*.md",
            "text": "*.txt", "txt": "*.txt",
            "json": "*.json", "yaml": "*.yaml", "yml": "*.yml",
            "html": "*.html", "css": "*.css",
        }
        pattern = lang_map.get(ext_or_lang.lower(), f"*{ext_or_lang}" if ext_or_lang.startswith(".") else f"*.{ext_or_lang}")
        if platform.system() == "Windows":
            return f"dir /s /b {pattern}", f"Find all {ext_or_lang} files"
        return f"find . -name \"{pattern}\" -type f", f"Find all {ext_or_lang} files"
    return None


def _try_count_lines(text: str) -> tuple[str, str] | None:
    """Match: count lines in files."""
    m = re.search(
        r"(?:count|how many)\s+(?:lines?|loc)\s+(?:in|of)\s+[\"']?([^\s\"']+)",
        text, re.IGNORECASE,
    )
    if m:
        target = m.group(1)
        if "*" in target or "." in target:
            return f"find . -name \"{target}\" | xargs wc -l", f"Count lines in {target} files"
        return f"wc -l {target}", f"Count lines in {target}"
    # "count lines of all python files"
    m2 = re.search(
        r"(?:count|how many)\s+(?:lines?|loc)\s+(?:of\s+)?(?:all\s+)?(\w+)\s+files?",
        text, re.IGNORECASE,
    )
    if m2:
        lang = m2.group(1)
        lang_map = {"python": "*.py", "py": "*.py", "javascript": "*.js", "js": "*.js", "java": "*.java"}
        pat = lang_map.get(lang.lower(), f"*.{lang}")
        return f"find . -name \"{pat}\" | xargs wc -l", f"Count lines in all {lang} files"
    return None


def _try_disk_usage(text: str) -> tuple[str, str] | None:
    """Match: disk usage, how much space, etc."""
    if re.search(r"(?:disk|space|storage)\s*(?:usage|used|free|left|available)", text, re.IGNORECASE):
        if platform.system() == "Windows":
            return "wmic logicaldisk get size,freespace,caption", "Check disk usage"
        return "df -h", "Show disk usage"
    return None


def _try_current_dir(text: str) -> tuple[str, str] | None:
    """Match: where am I, current directory, pwd."""
    if re.search(r"(?:where am i|current\s+dir|pwd|working\s+dir|which\s+dir)", text, re.IGNORECASE):
        return "pwd", "Show current working directory"
    return None


def _try_process_list(text: str) -> tuple[str, str] | None:
    """Match: show processes, running processes, etc."""
    if re.search(r"(?:show|list|display|running)\s*(?:processes|tasks|procs)", text, re.IGNORECASE):
        if platform.system() == "Windows":
            return "tasklist", "List running processes"
        return "ps aux", "List running processes"
    return None


def _try_system_info(text: str) -> tuple[str, str] | None:
    """Match: system info, os info, etc."""
    if re.search(r"(?:system|os|machine)\s*(?:info|information|details|version)", text, re.IGNORECASE):
        if platform.system() == "Windows":
            return "systeminfo", "Show system information"
        return "uname -a", "Show system information"
    return None


def _try_create_dir(text: str) -> tuple[str, str] | None:
    """Match: create/make directory/folder."""
    m = re.search(
        r"(?:create|make|mkdir)\s+(?:a\s+)?(?:directory|folder|dir)\s+(?:called\s+|named\s+)?[\"']?([^\s\"']+)",
        text, re.IGNORECASE,
    )
    if m:
        name = m.group(1)
        return f"mkdir -p {name}", f"Create directory '{name}'"
    return None


def _try_remove_file(text: str) -> tuple[str, str] | None:
    """Match: delete/remove a specific file."""
    m = re.search(
        r"(?:delete|remove|rm)\s+(?:the\s+)?(?:file\s+)?[\"']?([^\s\"']+\.\w+)[\"']?",
        text, re.IGNORECASE,
    )
    if m:
        name = m.group(1)
        return f"rm {name}", f"Delete file '{name}'"
    return None


def _try_cat_file(text: str) -> tuple[str, str] | None:
    """Match: show/read/cat file contents."""
    m = re.search(
        r"(?:show|read|cat|display|print|view)\s+(?:the\s+)?(?:contents?\s+of\s+)?(?:file\s+)?[\"']?([^\s\"']+\.\w+)[\"']?",
        text, re.IGNORECASE,
    )
    if m:
        name = m.group(1)
        return f"cat {name}", f"Display contents of '{name}'"
    return None


def _try_grep_search(text: str) -> tuple[str, str] | None:
    """Match: search for text in files."""
    m = re.search(
        r"(?:search|grep|find|look)\s+(?:for\s+)?[\"']([^\"']+)[\"']\s+(?:in\s+)?(?:all\s+)?(?:(\w+)\s+)?files?",
        text, re.IGNORECASE,
    )
    if m:
        query = m.group(1)
        ftype = m.group(2)
        if ftype:
            lang_map = {"python": "*.py", "py": "*.py", "javascript": "*.js", "js": "*.js"}
            pat = lang_map.get(ftype.lower(), f"*.{ftype}")
            return f'grep -rn "{query}" --include="{pat}" .', f"Search for '{query}' in {ftype} files"
        return f'grep -rn "{query}" .', f"Search for '{query}' in all files"
    return None


def _try_network(text: str) -> tuple[str, str] | None:
    """Match: ping, curl, ip address, etc."""
    # ping
    m = re.search(r"ping\s+([^\s]+)", text, re.IGNORECASE)
    if m:
        host = m.group(1)
        return f"ping -c 4 {host}", f"Ping {host}"
    # ip address
    if re.search(r"(?:my\s+)?ip\s*(?:address)?|what.+ip", text, re.IGNORECASE):
        if platform.system() == "Windows":
            return "ipconfig", "Show network configuration"
        return "ip addr show || ifconfig", "Show IP address"
    return None


def _try_git(text: str) -> tuple[str, str] | None:
    """Match: common git operations."""
    if re.search(r"git\s+status|show\s+git\s+status", text, re.IGNORECASE):
        return "git status", "Show git status"
    if re.search(r"git\s+log|show\s+(?:git\s+)?(?:commit\s+)?(?:history|log)", text, re.IGNORECASE):
        return "git log --oneline -20", "Show recent git history"
    if re.search(r"git\s+diff|show\s+(?:git\s+)?(?:changes|diff)", text, re.IGNORECASE):
        return "git diff", "Show git diff"
    if re.search(r"(?:which|what)\s+(?:git\s+)?branch", text, re.IGNORECASE):
        return "git branch", "Show git branches"
    return None


def _try_date_time(text: str) -> tuple[str, str] | None:
    """Match: current date/time."""
    if re.search(r"(?:what|current|show)\s*(?:is\s+)?(?:the\s+)?(?:date|time|today)", text, re.IGNORECASE):
        return "date", "Show current date and time"
    return None


# Ordered list of all matchers
_MATCHERS = [
    _try_list_files,
    _try_find_files,
    _try_count_lines,
    _try_disk_usage,
    _try_current_dir,
    _try_process_list,
    _try_system_info,
    _try_create_dir,
    _try_remove_file,
    _try_cat_file,
    _try_grep_search,
    _try_network,
    _try_git,
    _try_date_time,
]


def try_local_conversion(text: str) -> dict | None:
    """Try to convert natural language to a shell command locally (no LLM).

    Returns a dict with {intent, command, reason, risk_level} if matched,
    or None if the input cannot be handled locally.
    """
    text = text.strip()
    if not text:
        return None

    for matcher in _MATCHERS:
        result = matcher(text)
        if result:
            command, reason = result
            # Assess risk locally
            from .safety import check_command
            safety = check_command(command)
            risk = "low"
            if safety["level"] == "warn":
                risk = "medium"
            elif safety["level"] == "deny":
                risk = "high"

            return {
                "intent": "run_command",
                "command": command,
                "reason": reason,
                "risk_level": risk,
                "source": "local_nlp",
                "safety_check": safety,
            }

    return None
