"""Task 4.1: MCP-style tool registry. Tools register with name/description/parameters."""

import json
from typing import Any, Callable, Awaitable

# Global tool registry
_TOOLS: dict[str, dict] = {}

# Permission levels per tool
PERMISSION_LEVELS = {
    "ALLOW": "Auto-execute, no confirmation needed",
    "ASK": "Requires user confirmation before execution",
    "DENY": "Blocked, cannot be executed",
}

# Permission config: tool_name -> "ALLOW" | "ASK" | "DENY"
_PERMISSIONS: dict[str, str] = {}

# Default permissions by category
DEFAULT_PERMISSIONS = {
    "read_file": "ALLOW",
    "list_directory": "ALLOW",
    "get_system_info": "ALLOW",
    "file_exists": "ALLOW",
    "search_files": "ALLOW",
    "count_lines": "ALLOW",
    "write_file": "ASK",
    "delete_file": "DENY",
    "fetch_url": "ASK",
}


def register_tool(
    name: str,
    description: str,
    parameters: dict,
    handler: Callable[..., Awaitable[Any]],
    permission: str = "ASK",
):
    """Register a tool in MCP style."""
    _TOOLS[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }
    _PERMISSIONS[name] = DEFAULT_PERMISSIONS.get(name, permission) # 默认为permission=ASK


def get_tool(name: str) -> dict | None:
    return _TOOLS.get(name)


def list_tools() -> list[dict]:
    """List all registered tools (without handler, for LLM consumption)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in _TOOLS.values()
    ]


def get_tool_permission(name: str) -> str:
    return _PERMISSIONS.get(name, "ASK")


async def execute_tool(name: str, arguments: dict) -> Any:
    """Execute a registered tool with given arguments."""
    tool = _TOOLS.get(name)
    if not tool:
        return f"[Error] Tool '{name}' not found."
    try:
        return await tool["handler"](**arguments)
    except Exception as e:
        return f"[Tool Error] {name}: {e}"
