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
- **Offline Shell Parser** (Bonus 2): Regex + jieba based local NL→command parsing with risk scoring
- **A2A Runtime** (Bonus 3): In-process structured request/response routing via `src/a2a`
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

Create a `.env` file in the project root and fill in your API credentials:

Edit `.env`:
```
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

Optional LLM tuning knobs:
```
OPENAI_TEMPERATURE_STREAM=0.7
OPENAI_TEMPERATURE_JSON=0.3
OPENAI_TEMPERATURE_TOOL=0.3
OPENAI_JSON_RETRY_COUNT=2
```

- Temperature valid range is `0.0` to `2.0` (values outside range are clamped).
- `OPENAI_JSON_RETRY_COUNT` minimum is `1`.

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
ACEE/
├── run.py                  # Entry point
├── requirements.txt
├── .env                    # API keys (not committed)
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
    ├── offline_shell_parser.py # Bonus 2: Local NL→command parser
    ├── a2a/                # Bonus 3: A2A runtime/models/transport
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

### Bonus 2: Offline Shell Parser

`src/offline_shell_parser.py` provides local rule-based parsing for shell tasks.

- Uses regex + optional `jieba` tokenization for Chinese-first intent parsing.
- Supports structured safety metadata (`risk_level`, `risk_score`, `risk_reasons`).
- Works with `ACEE_SHELL_MODE` in `auto` / `offline` / `llm` modes.

### Bonus 3: A2A Runtime

The A2A layer is implemented under `src/a2a` with structured envelopes and transport:

- `A2ARequest` / `A2AResponse` / `TaskState` in `src/a2a/models.py`
- `InProcessTransport` in `src/a2a/transport.py`
- `A2ARuntime` facade in `src/a2a/runtime.py`

```python
from src.a2a import A2ARuntime

runtime = A2ARuntime()
classification = await runtime.classify_intent("list files", history=[])
```

