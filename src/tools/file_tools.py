"""Task 4.2: File operation tools (MCP style)."""

import os
import glob as glob_mod
from .registry import register_tool


async def read_file(path: str) -> str:
    """Read and return the contents of a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 10000:
            return content[:10000] + f"\n... [truncated, total {len(content)} chars]"
        return content
    except Exception as e:
        return f"[Error] Cannot read file: {e}"


async def write_file(path: str, content: str) -> str:
    """Write content to a file (creates or overwrites)."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"[Error] Cannot write file: {e}"


async def list_directory(path: str = ".") -> str:
    """List files and directories in a path."""
    try:
        entries = os.listdir(path)
        result = []
        for entry in sorted(entries)[:100]:
            full = os.path.join(path, entry)
            tag = "[DIR]" if os.path.isdir(full) else "[FILE]"
            size = ""
            if os.path.isfile(full):
                s = os.path.getsize(full)
                size = f" ({s} bytes)"
            result.append(f"  {tag} {entry}{size}")
        header = f"Contents of {os.path.abspath(path)} ({len(entries)} items):"
        return header + "\n" + "\n".join(result)
    except Exception as e:
        return f"[Error] Cannot list directory: {e}"


async def file_exists(path: str) -> str:
    """Check if a file or directory exists."""
    if os.path.exists(path):
        kind = "directory" if os.path.isdir(path) else "file"
        return f"Yes, '{path}' exists (it is a {kind})."
    return f"No, '{path}' does not exist."


async def search_files(pattern: str, directory: str = ".") -> str:
    """Search for files matching a glob pattern."""
    try:
        full_pattern = os.path.join(directory, pattern)
        matches = glob_mod.glob(full_pattern, recursive=True)
        if not matches:
            return f"No files matching '{pattern}' in {directory}"
        result = [f"Found {len(matches)} matches:"]
        for m in matches[:50]:
            result.append(f"  {m}")
        if len(matches) > 50:
            result.append(f"  ... and {len(matches) - 50} more")
        return "\n".join(result)
    except Exception as e:
        return f"[Error] Search failed: {e}"


async def count_lines(path: str) -> str:
    """Count the number of lines in a file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            n = sum(1 for _ in f)
        return f"{path}: {n} lines"
    except Exception as e:
        return f"[Error] Cannot count lines: {e}"


def register_all():
    register_tool(
        name="read_file",
        description="Read the contents of a file at the given path. Use this when you need to examine file contents.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Absolute or relative file path"}},
            "required": ["path"],
        },
        handler=read_file,
        permission="ALLOW",
    )
    register_tool(
        name="write_file",
        description="Write content to a file, creating it if it doesn't exist. Use for creating or modifying files.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write to"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        handler=write_file,
        permission="ASK",
    )
    register_tool(
        name="list_directory",
        description="List all files and subdirectories in a directory. Use to explore folder structure.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Directory path (default: current dir)", "default": "."}},
            "required": [],
        },
        handler=list_directory,
        permission="ALLOW",
    )
    register_tool(
        name="file_exists",
        description="Check whether a file or directory exists at the given path.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to check"}},
            "required": ["path"],
        },
        handler=file_exists,
        permission="ALLOW",
    )
    register_tool(
        name="search_files",
        description="Search for files matching a glob pattern (e.g. '**/*.py'). Use to find files by name.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern like '**/*.py'"},
                "directory": {"type": "string", "description": "Base directory", "default": "."},
            },
            "required": ["pattern"],
        },
        handler=search_files,
        permission="ALLOW",
    )
    register_tool(
        name="count_lines",
        description="Count the number of lines in a text file.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to the file"}},
            "required": ["path"],
        },
        handler=count_lines,
        permission="ALLOW",
    )
