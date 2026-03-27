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
- **Orchestrator Agent**: Intent classification with context injection (OS, cwd, directory listing)
- **Shell Agent**: Natural language → shell commands with structured JSON output
- **Safety Engine**: Dual-layer protection (LLM risk assessment + local rule engine)
- **Tool Agent**: MCP-style tools with LLM function calling and ReAct loop
- **Permission System**: Three-tier (ALLOW / ASK / DENY) per tool
- **Memory Agent**: Persistent cross-session memory (JSON-based)

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

### Input Modes

| Mode | Prefix | Example | Behavior |
|------|--------|---------|----------|
| Direct Shell | `/` | `/ls -la` | Execute immediately, no LLM |
| Natural Language | (none) | `list all python files` | LLM intent classification → agent dispatch |
| Memory | `!memory` | `!memory save this is a Flask project` | Save/search persistent memory |

### Keyboard Shortcuts

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
    ├── tui.py              # Task 1: Textual TUI
    ├── process_manager.py  # Task 1.2: Async subprocess
    ├── llm_client.py       # Task 2.1: OpenAI API client
    ├── orchestrator.py     # Task 2.2-2.3: Intent + dispatch
    ├── shell_agent.py      # Task 3.1: NL → shell command
    ├── safety.py           # Task 3.2: Safety rule engine
    ├── tool_agent.py       # Task 4.4: Tool Agent + ReAct
    ├── memory_agent.py     # Bonus 1: Memory
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
