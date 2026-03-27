"""Task 4.2: System information tools (MCP style)."""

import os
import platform
import shutil
from .registry import register_tool


async def get_system_info() -> str:
    """Get basic system information."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
        "cwd": os.getcwd(),
    }
    lines = [f"  {k}: {v}" for k, v in info.items()]
    return "System Information:\n" + "\n".join(lines)


async def get_disk_usage(path: str = "/") -> str:
    """Get disk usage for a given path."""
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        pct = (usage.used / usage.total) * 100
        return (
            f"Disk usage for {path}:\n"
            f"  Total: {total_gb:.1f} GB\n"
            f"  Used:  {used_gb:.1f} GB ({pct:.1f}%)\n"
            f"  Free:  {free_gb:.1f} GB"
        )
    except Exception as e:
        return f"[Error] Cannot get disk usage: {e}"


async def get_env_var(name: str) -> str:
    """Get the value of an environment variable."""
    val = os.environ.get(name)
    if val is None:
        return f"Environment variable '{name}' is not set."
    # Mask sensitive values
    lower = name.lower()
    if any(s in lower for s in ("key", "secret", "password", "token")):
        return f"{name} = {'*' * min(len(val), 8)}... (masked)"
    return f"{name} = {val}"


def register_all():
    register_tool(
        name="get_system_info",
        description="Get OS, architecture, Python version, CPU count, and current working directory.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=get_system_info,
        permission="ALLOW",
    )
    register_tool(
        name="get_disk_usage",
        description="Get disk usage (total, used, free space) for a given path.",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path to check", "default": "/"}},
            "required": [],
        },
        handler=get_disk_usage,
        permission="ALLOW",
    )
    register_tool(
        name="get_env_var",
        description="Get the value of an environment variable by name. Sensitive values are masked.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Environment variable name"}},
            "required": ["name"],
        },
        handler=get_env_var,
        permission="ALLOW",
    )
