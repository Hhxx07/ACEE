"""Bonus 4: AGENTS.md support — dynamic agent discovery and configuration.

Reads an AGENTS.md file in the project root to discover and configure agents.
This allows users to customize agent behavior without modifying code.

Example AGENTS.md format:

    # Agents Configuration

    ## shell_agent
    - description: Converts natural language to shell commands
    - enabled: true
    - priority: high
    - custom_rules:
      - Always use 'ls -la' instead of 'ls' on Linux
      - Prefer 'rg' over 'grep' if available

    ## tool_agent
    - description: Uses MCP tools to fulfill structured tasks
    - enabled: true
    - priority: medium

    ## custom_agent
    - description: A custom agent for project-specific tasks
    - enabled: true
    - system_prompt: You are a specialist in Python data analysis.
    - tools: read_file, write_file, search_files
"""

import os
import re
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for a single agent loaded from AGENTS.md."""
    name: str
    description: str = ""
    enabled: bool = True
    priority: str = "medium"
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    custom_rules: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# Global registry of loaded agent configs
_agent_configs: dict[str, AgentConfig] = {}

# Default AGENTS.md search paths
_SEARCH_PATHS = [
    "AGENTS.md",
    ".agents.md",
    ".config/agents.md",
]


def _parse_agents_md(content: str) -> dict[str, AgentConfig]:
    """Parse AGENTS.md content into AgentConfig objects."""
    configs = {}
    current_agent = None
    current_list_key = None

    for line in content.split("\n"):
        line_stripped = line.strip()

        # Agent header: ## agent_name
        m = re.match(r"^##\s+(\w+)", line_stripped)
        if m:
            name = m.group(1)
            current_agent = AgentConfig(name=name)
            configs[name] = current_agent
            current_list_key = None
            continue

        if current_agent is None:
            continue

        # Key-value: - key: value
        m = re.match(r"^-\s+(\w+):\s*(.+)?$", line_stripped)
        if m:
            key = m.group(1)
            value = (m.group(2) or "").strip()

            if key == "description":
                current_agent.description = value
            elif key == "enabled":
                current_agent.enabled = value.lower() in ("true", "yes", "1")
            elif key == "priority":
                current_agent.priority = value
            elif key == "system_prompt":
                current_agent.system_prompt = value
            elif key == "tools":
                current_agent.tools = [t.strip() for t in value.split(",") if t.strip()]
            elif key == "custom_rules":
                current_list_key = "custom_rules"
                # If value is on the same line
                if value:
                    current_agent.custom_rules.append(value)
            else:
                current_agent.extra[key] = value
                current_list_key = None
            continue

        # List item under a list key: - item
        if current_list_key and re.match(r"^\s+-\s+", line):
            item = re.sub(r"^\s+-\s+", "", line).strip()
            if current_list_key == "custom_rules":
                current_agent.custom_rules.append(item)
            continue

        # Reset list key on non-list content
        if line_stripped and not line_stripped.startswith("#"):
            current_list_key = None

    return configs


def load_agents_md(base_dir: str | None = None) -> dict[str, AgentConfig]:
    """Load agent configurations from AGENTS.md.

    Searches in the project root and common locations.
    Returns the loaded configs and caches them globally.
    """
    global _agent_configs
    base = base_dir or os.getcwd()

    for rel_path in _SEARCH_PATHS:
        full_path = os.path.join(base, rel_path)
        if os.path.isfile(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                _agent_configs = _parse_agents_md(content)
                return _agent_configs
            except Exception:
                pass

    # No AGENTS.md found — use defaults
    _agent_configs = {}
    return _agent_configs


def get_agent_config(name: str) -> AgentConfig | None:
    """Get the configuration for a specific agent."""
    return _agent_configs.get(name)


def is_agent_enabled(name: str) -> bool:
    """Check if an agent is enabled (defaults to True if not configured)."""
    config = _agent_configs.get(name)
    if config is None:
        return True
    return config.enabled


def get_custom_rules(name: str) -> list[str]:
    """Get custom rules for an agent (for system prompt injection)."""
    config = _agent_configs.get(name)
    if config is None:
        return []
    return config.custom_rules


def get_all_configs() -> dict[str, AgentConfig]:
    """Get all loaded agent configurations."""
    return dict(_agent_configs)


def create_default_agents_md(path: str | None = None):
    """Create a default AGENTS.md file."""
    path = path or os.path.join(os.getcwd(), "AGENTS.md")
    content = """# Agents Configuration
#
# This file configures the multi-agent CLI system.
# Uncomment and modify settings as needed.

## orchestrator
- description: Routes user requests to the appropriate sub-agent
- enabled: true
- priority: high

## shell_agent
- description: Converts natural language to safe shell commands
- enabled: true
- priority: high
- custom_rules:
  - Prefer safe alternatives for destructive operations
  - Use long flags for readability in complex commands

## tool_agent
- description: Uses MCP tools for structured tasks (file I/O, system info, HTTP)
- enabled: true
- priority: medium

## memory_agent
- description: Manages persistent cross-session memory
- enabled: true
- priority: low
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
