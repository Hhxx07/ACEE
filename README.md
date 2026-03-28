# Multi-Agent CLI System

A terminal-based multi-agent system that uses LLM to understand natural language and dispatch tasks to specialized agents.

## Architecture

```
User Input
    │
    ▼
┌──────────────┐
│ Orchestrator │──→ Intent Classification (LLM + JSON Schema)
│    Agent     │
└──────┬───────┘
       │
   ┌───┼───────────────┐
   ▼   ▼               ▼
┌──────┐ ┌──────────┐ ┌────────────┐
│Shell │ │  Tool    │ │  Direct    │
│Agent │ │  Agent   │ │  Answer    │
└──┬───┘ └────┬─────┘ └────────────┘
   │          │
   ▼          ▼
Safety     MCP Tools
Engine     (File/System/Network)
```

## Features

- **TUI Interface** (Textual): Input bar, scrollable output area, live status bar
- **Streaming Output**: Real-time subprocess output and LLM token streaming
- **Orchestrator Agent**: Intent classification with context injection (OS, cwd, directory listing, git status, env vars)
- **Shell Agent**: Natural language → shell commands with structured JSON output
- **Safety Engine**: Dual-layer protection (LLM risk assessment + local rule engine)
- **Tool Agent**: MCP-style tools with LLM function calling and ReAct loop
- **Permission System**: Three-tier (ALLOW / ASK / DENY) per tool
- **Memory Agent**: Persistent cross-session memory (JSON-based)
- **Local NLP** (Bonus 2): Keyword-based NL→command conversion without LLM for common operations
- **A2A Protocol** (Bonus 3): Standardized agent-to-agent messaging with message bus
- **AGENTS.md** (Bonus 4): Dynamic agent discovery and configuration via config file
- **Tab Completion** (Task 3.3): Auto-complete commands and file names with Tab key
- **Command History**: Navigate previous commands with Up/Down arrows

## Setup

### Requirements

- Python 3.10+ (recommended 3.11)
- LLM API Key (OpenAI / DeepSeek / Gemini / etc.)

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

For **DeepSeek**:
```
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

## Usage

```bash
python run.py
```

## Offline Shell Parser

`Shell Agent` supports an offline command parser in `src/offline_shell_parser.py`.

- Uses **regex + local NLP (`jieba`)** for Chinese-first intent parsing.
- Produces structured risk output:
    - `risk_level`: `low | medium | high`
    - `risk_score`: numeric confidence in `[0, 1]`
    - `risk_reasons`: matched risk factors (for explainability)
- In `auto` mode, parser can set `allow_fallback=True` to let LLM handle unclear intents.

Configure with `ACEE_SHELL_MODE`:

- `auto` (default): try offline parser first, fallback to LLM only if allowed
- `offline`: offline parser only
- `llm`: skip offline parser and call LLM directly

### Input Modes

| Mode | Prefix | Example | Behavior |
|------|--------|---------|----------|
| Direct Shell | `/` | `/ls -la` | Execute immediately, no LLM |
| Natural Language | (none) | `list all python files` | LLM intent classification → agent dispatch |
| Memory | `!memory` | `!memory save this is a Flask project` | Save/search persistent memory |

### Keyboard Shortcuts

- **Tab**: Auto-complete commands and file names
- **Up/Down**: Navigate command history
- **Ctrl+C**: Quit
- **Ctrl+L**: Clear output

## Project Structure

```
assignment_A/
├── run.py                  # Entry point
├── requirements.txt
├── .env                    # API keys (not committed)
├── .env.example
├── README.md
├── memory.json             # Persistent memory store
└── src/
    ├── main.py             # App bootstrap
    ├── tui.py              # Task 1: Textual TUI + Tab completion + history
    ├── process_manager.py  # Task 1.2: Async subprocess
    ├── llm_client.py       # Task 2.1: OpenAI API client
    ├── orchestrator.py     # Task 2.2-2.3: Intent + dispatch + rich context
    ├── shell_agent.py      # Task 3.1-3.3: NL → shell + clarification
    ├── safety.py           # Task 3.2: Safety rule engine
    ├── tool_agent.py       # Task 4.4: Tool Agent + ReAct
    ├── memory_agent.py     # Bonus 1: Memory
    ├── local_nlp.py        # Bonus 2: Local NL→command (no LLM)
    ├── a2a_protocol.py     # Bonus 3: Agent-to-Agent protocol
    ├── agents_md.py        # Bonus 4: AGENTS.md loader
    └── tools/
        ├── registry.py     # Task 4.1: MCP-style registry
        ├── file_tools.py   # Task 4.2: File operations
        ├── system_tools.py # Task 4.2: System info
        └── network_tools.py# Task 4.2: HTTP/API tools
```

## Tool Categories (MCP)

| Category | Tools | Permission |
|----------|-------|------------|
| File | read_file, write_file, list_directory, file_exists, search_files, count_lines | ALLOW / ASK |
| System | get_system_info, get_disk_usage, get_env_var | ALLOW |
| Network | fetch_url, call_rest_api | ASK |

## Bonus Features

### Bonus 2: Local NLP (No LLM)

Common natural language patterns are converted to shell commands locally using keyword matching, avoiding API latency for simple operations like:
- "list files" → `ls -la .`
- "find python files" → `find . -name "*.py" -type f`
- "count lines in main.py" → `wc -l main.py`
- "git status" → `git status`
- "ping google.com" → `ping -c 4 google.com`

Falls back to LLM for complex or ambiguous requests.

### Bonus 3: A2A Protocol

Standardized agent-to-agent messaging via `AgentMessage` dataclass and `AgentBus`:

```python
# Sending a message between agents
msg = create_request("orchestrator", "shell_agent", "generate_command",
                     user_input="list files", task_description="List directory contents")
response = await bus.send(msg)
```

Features: unique message IDs, request/response/error types, message logging, event listeners.

### Bonus 4: AGENTS.md

Place an `AGENTS.md` file in the project root to configure agents:

```markdown
## shell_agent
- description: Converts natural language to shell commands
- enabled: true
- custom_rules:
  - Prefer safe alternatives for destructive operations
  - Use long flags for readability
```

Custom rules are injected into agent system prompts automatically.
