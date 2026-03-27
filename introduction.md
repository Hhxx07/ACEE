# ACEE Project Introduction

## 1. Project Purpose

ACEE is a terminal-based multi-agent system. It accepts natural language input, decides intent, dispatches to specialized agents, executes actions, and streams results back to the user.

Current architecture supports two invocation styles:

1. Legacy direct function calls between modules.
2. In-process A2A-style protocol invocation via adapters and transport.

## 2. Entry and Startup

Execution starts from [run.py](run.py):

1. Adds project root to `sys.path`.
2. Imports `main()` from [src/main.py](src/main.py).
3. Launches the Textual TUI app.

In [src/main.py](src/main.py):

1. Loads `.env` from project root.
2. Creates and runs `AgentCLI` from [src/tui.py](src/tui.py).

Run command:

```bash
python run.py
```

## 3. High-Level Runtime Flow

Main request loop is in [src/tui.py](src/tui.py):

1. User submits input in TUI.
2. Input is routed into one of three modes:
   - Direct shell mode (`/` prefix)
   - Memory command mode (`!memory`)
   - Orchestrated NL mode (default)
3. Output is rendered to RichLog with status updates.

### 3.1 Direct Shell Mode

Path: `on_input_submitted` -> `_handle_shell_direct` -> [src/process_manager.py](src/process_manager.py)

Behavior:

1. Executes command immediately with async subprocess.
2. Streams stdout/stderr line by line.
3. Shows exit code when done.

Important: this path does not pass through [src/safety.py](src/safety.py).

### 3.2 Memory Command Mode

Supported commands:

1. `!memory save <text>`
2. `!memory search <query>`

Implementation: [src/memory_agent.py](src/memory_agent.py), persisted in `memory.json` at repo root.

### 3.3 Orchestrated Natural Language Mode

Path: `on_input_submitted` -> `_handle_orchestrated`

Sequence:

1. Read relevant memory context.
2. Classify intent with orchestrator.
3. Dispatch by intent:
   - `shell_agent`
   - `tool_agent`
   - `clarification`
   - `direct_answer`
4. Render response and append to conversation history.

## 4. Core Modules and Responsibilities

### 4.1 LLM Client

File: [src/llm_client.py](src/llm_client.py)

Provides:

1. `chat`: normal completion.
2. `chat_stream`: streaming completion.
3. `chat_json`: expects JSON object, retries once on JSON parse failure.
4. `chat_function_call`: OpenAI-style tool calling wrapper.

Environment variables used:

1. `OPENAI_API_KEY`
2. `OPENAI_BASE_URL`
3. `OPENAI_MODEL`

### 4.2 Orchestrator Agent

File: [src/orchestrator.py](src/orchestrator.py)

Purpose:

1. Inject OS/cwd/dir context.
2. Classify user intent to routing decision.
3. Return structured JSON with fields like `intent`, `reasoning`, `confidence`, `task_description`.

### 4.3 Shell Agent

File: [src/shell_agent.py](src/shell_agent.py)

Purpose:

1. Convert NL task to shell command JSON.
2. Support offline parser bridge and fallback logic.
3. Enforce local safety post-check.

Shell mode flag:

1. `ACEE_SHELL_MODE=auto|offline|llm`

Behavior summary:

1. `auto`: try offline parser first, fallback to LLM when allowed.
2. `offline`: only offline parser; if unresolved, refuse.
3. `llm`: skip offline parser and use LLM directly.

### 4.4 Offline Shell Parser

File: [src/offline_shell_parser.py](src/offline_shell_parser.py)

Design:

1. Rule-based intent detection.
2. Chinese tokenization via `jieba` when available.
3. Path/extension/PID extraction.
4. Risk scoring and reason generation.
5. Command template generation by OS.

### 4.5 Safety Engine

File: [src/safety.py](src/safety.py)

Provides:

1. `DENY_PATTERNS`: hard block patterns.
2. `WARN_PATTERNS`: caution-required patterns.
3. `check_command(command)` -> `safe|warn|deny` with reasons.

### 4.6 Tool Agent

File: [src/tool_agent.py](src/tool_agent.py)

Design:

1. ReAct-style loop with max iterations.
2. LLM chooses tool calls.
3. Executes tools via registry.
4. Appends tool observations back to message history.

Permission integration:

1. `ALLOW`: execute.
2. `ASK`: currently auto-allow with warning output.
3. `DENY`: block.

### 4.7 Tool Registry and Built-in Tools

Files:

1. [src/tools/registry.py](src/tools/registry.py)
2. [src/tools/file_tools.py](src/tools/file_tools.py)
3. [src/tools/system_tools.py](src/tools/system_tools.py)
4. [src/tools/network_tools.py](src/tools/network_tools.py)

Registry handles:

1. Tool registration.
2. Tool schema listing for LLM.
3. Permission lookup and override.
4. Execution dispatch and error wrapping.

### 4.8 Process Manager

File: [src/process_manager.py](src/process_manager.py)

Provides async subprocess execution with streaming output callbacks and completion callback.

### 4.9 Memory Agent

File: [src/memory_agent.py](src/memory_agent.py)

Capabilities:

1. Save memory entries.
2. Search by keyword scoring.
3. Return top relevant context for current input.

## 5. A2A Layer (Current Implementation)

A2A code lives in [src/a2a/__init__.py](src/a2a/__init__.py), [src/a2a/models.py](src/a2a/models.py), [src/a2a/transport.py](src/a2a/transport.py), [src/a2a/agents.py](src/a2a/agents.py), [src/a2a/runtime.py](src/a2a/runtime.py).

### 5.1 What Is Implemented

1. A2A request/response envelope models.
2. Task lifecycle states (`created`, `running`, `waiting`, `completed`, `failed`, `cancelled`).
3. Unified `ErrorEnvelope`.
4. In-process transport dispatch by `to_agent`.
5. Adapter agents for orchestrator/shell/tool/memory.
6. Runtime facade used by TUI.

### 5.2 A2A Mode Switch in TUI

In [src/tui.py](src/tui.py), mode is controlled by:

1. `ACEE_A2A_MODE=off|shadow|on`

Current behavior:

1. `off`: legacy direct calls.
2. `on`: route through `A2ARuntime`.
3. `shadow`: currently same behavior as `on` (no dual-run diff yet).

## 6. Configuration Summary

Primary environment variables:

1. `OPENAI_API_KEY`
2. `OPENAI_BASE_URL`
3. `OPENAI_MODEL`
4. `ACEE_SHELL_MODE`
5. `ACEE_A2A_MODE`

## 7. Data and State

Persistent state:

1. `memory.json` stores memory entries.

In-memory runtime state:

1. TUI conversation history.
2. Current A2A runtime instance when enabled.
3. Tool registry and permission tables.

## 8. Safety and Risk Boundaries

1. Shell agent path applies local safety engine post-check.
2. Tool calls are permission-gated.
3. Direct shell path bypasses safety rules.
4. Network tools are default `ASK` permissions.

## 9. Current Gaps and Technical Debt

1. `ACEE_A2A_MODE=shadow` has no dedicated shadow comparison pipeline yet.
2. Direct shell mode bypasses safety engine.
3. Test directory exists but currently has no test files.
4. `a2a-sdk` is listed in requirements but not imported in source today.

## 10. How to Extend

### 10.1 Add a New Agent

1. Implement core logic module in `src/`.
2. Add A2A adapter in [src/a2a/agents.py](src/a2a/agents.py).
3. Register adapter in [src/a2a/runtime.py](src/a2a/runtime.py).
4. Add routing logic in [src/tui.py](src/tui.py).

### 10.2 Add a New Tool

1. Implement async tool handler under `src/tools/`.
2. Register tool schema and permission in `register_all()`.
3. Tool agent can then call it via function-calling loop.

### 10.3 Strengthen Safety

1. Extend deny/warn regex patterns in [src/safety.py](src/safety.py).
2. Optionally enforce safety checks for direct shell mode.
3. Add logging/auditing for blocked or risky commands.

## 11. Quick Mental Model

Think of ACEE as:

1. TUI orchestrator front-end.
2. LLM-guided intent and execution engine.
3. Safety and permission guardrails.
4. Optional protocolized A2A invocation layer for future distributed evolution.

This combination makes the project usable as a CLI assistant now, while preserving a migration path toward stricter agent-to-agent protocol architecture.
