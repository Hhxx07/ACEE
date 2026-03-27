# Agents Configuration
#
# This file configures the multi-agent CLI system.
# Modify settings below to customize agent behavior.

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
  - Always confirm before executing commands that modify files

## tool_agent
- description: Uses MCP tools for structured tasks (file I/O, system info, HTTP)
- enabled: true
- priority: medium

## memory_agent
- description: Manages persistent cross-session memory
- enabled: true
- priority: low
