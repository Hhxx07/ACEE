# ACEE Multi-Agent CLI System

这是一个基于终端的多 Agent CLI 系统。它通过编排代理识别用户意图，将请求分发到 Shell Agent、Tool Agent 或 Direct Answer 路径，并在 Textual TUI 中流式展示结果。

项目核心目标：
- 把自然语言请求转换为可执行动作（命令执行或工具调用）
- 在执行链路中引入可扩展的安全、权限和记忆机制
- 使用统一的 A2A（Agent-to-Agent）协议封装模块间通信，便于后续扩展

## 1. 核心能力

- Textual TUI 交互界面：输入框、日志流、状态栏、快捷键
- 意图编排（Orchestrator）：`shell_agent | tool_agent | direct_answer | clarification`
- Shell 命令生成（Shell Agent）：支持 `llm | auto | offline` 三种模式
- 本地安全引擎（Safety）：正则规则 `safe | warn | deny`
- Tool Agent ReAct 循环：基于 LLM function-calling 选择并调用工具
- 工具权限模型：`ALLOW | ASK | DENY`
- 持久化记忆（Memory Agent）：`memory.json` 存储、检索、启动注入
- A2A Runtime：统一 Request/Response 封装与 in-process transport
- 可选 MCP 服务器接入（stdio JSON-RPC）

## 2. 系统架构

```text
User Input (TUI)
    |
    v
Orchestrator (intent classification)
    |
    +--> Shell Agent --> Safety --> Process Manager --> Stream Output
    |
    +--> Tool Agent (ReAct + Function Calling) --> Tool Registry / MCP
    |
    +--> Direct Answer (LLM stream)
    |
    +--> Clarification

Memory Agent <--> memory.json
A2A Runtime wraps orchestrator/shell/tool/memory adapters
```

## 3. 启动流程

实际入口链路：

1. `run.py` 启动，导入 `src.main.main`
2. `src/main.py` 加载 `.env`，初始化 `MCPAdapter`
3. 注入 TUI `on_mount`（如果配置了 `MCP_SERVERS`，先初始化 MCP）
4. 启动 `AgentCLI`（Textual 应用）

启动命令：

```bash
python run.py
```

## 4. 用户输入模式

`src/tui.py` 中，输入优先级如下：

1. `/help`：本地帮助渲染（不走 Agent）
2. `/...`：直接 Shell 执行（不经过 Orchestrator/Safety）
3. `!memory ...`：记忆指令（保存或搜索）
4. 其他输入：走 Orchestrator 完整链路

支持命令：
- `!memory save <text>`
- `!memory search <query>`

常用快捷键：
- `Tab`：命令/文件名补全
- `Up/Down`：命令历史
- `Ctrl+L`：清屏
- `Ctrl+C`：退出
- `Esc`：关闭澄清面板

## 5. 安装与环境

### Python 依赖

```bash
pip install -r requirements.txt
```

### 配置 `.env`

最小配置：

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

DeepSeek 示例：

```env
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

LLM 调优项：

```env
OPENAI_TEMPERATURE_STREAM=0.7
OPENAI_TEMPERATURE_JSON=0.3
OPENAI_TEMPERATURE_TOOL=0.3
OPENAI_JSON_RETRY_COUNT=2

ACEE_LLM_DEBUG_LOG=0
ACEE_LLM_DEBUG_LOG_PATH=./logs/llm_responses.jsonl
```

Agent 行为开关：

```env
ACEE_SHELL_MODE=llm
ACEE_ORCH_OFFLINE_FIRST=1
ACEE_TAG_FALLBACK_MODE=off
MCP_SERVERS=[]
```

说明：
- `OPENAI_TEMPERATURE_*` 范围会被限制在 `0.0~2.0`
- `OPENAI_JSON_RETRY_COUNT` 最小值为 `1`
- `ACEE_SHELL_MODE` 支持 `llm | auto | offline`

## 6. 关键模块说明

- `src/orchestrator.py`
  - 负责意图分类与路由建议
  - 可启用离线优先预分类（`ACEE_ORCH_OFFLINE_FIRST=1`）

- `src/shell_agent.py`
  - 生成命令计划（JSON）
  - 支持离线解析器 `src/offline_shell_parser.py`
  - 在执行前调用 `src/safety.py` 进行命令安全检查

- `src/tool_agent.py`
  - LLM function-calling + ReAct 循环（最多 5 轮）
  - 调用本地注册工具和 MCP 工具

- `src/memory_agent.py`
  - 持久化 `memory.json`
  - 启动记忆注入、相关记忆检索、手动搜索

- `src/a2a/`
  - `models.py`：协议模型（Request/Response/ErrorEnvelope/TaskState）
  - `transport.py`：in-process transport
  - `agents.py`：对现有 agent 的 A2A 适配器
  - `runtime.py`：统一门面调用

- `src/tools/`
  - `registry.py`：工具注册与权限控制
  - `file_tools.py`：文件类工具
  - `system_tools.py`：系统信息工具
  - `network_tools.py`：网络请求工具
  - `mcp_adaptor.py`：MCP 服务器桥接

## 7. 权限与安全

### 权限模型

`src/tools/registry.py` 定义三档权限：
- `ALLOW`：自动执行
- `ASK`：需要确认
- `DENY`：禁止执行

当前实现细节：
- Tool Agent 对 `ASK` 会提示警告，但当前逻辑为自动放行（未阻塞等待用户确认）

### 安全引擎

`src/safety.py` 使用本地规则（正则）分级：
- `deny`：高危直接拦截（如 `rm -rf`, `mkfs`, `dd`, `shutdown` 等）
- `warn`：高风险提醒（如 `sudo`, `git push --force`, 管道执行脚本等）
- `safe`：正常执行

注意：
- 以 `/` 前缀触发的“直接 shell 模式”不经过 `Safety`，这是当前系统的已知风险边界。

## 8. 测试现状

`tests/` 已包含以下方向：
- Orchestrator 离线优先路径与上下文注入
- A2A 历史上下文传递
- Tool/Shell prompt 历史注入
- Echo Agent 协议测试
- MCP 连接测试脚本

说明：
- 部分测试依赖真实环境变量（如 `OPENAI_API_KEY` 或 `MCP_SERVERS`）
- 仍有若干端到端交互路径可继续补测（如 TUI 澄清面板与 direct shell 安全策略）

## 9. 项目结构

```text
ACEE/
├── run.py
├── requirements.txt
├── README.md
├── AGENTS.md
├── memory.json
├── logs/
│   └── llm_responses.jsonl
├── src/
│   ├── main.py
│   ├── tui.py
│   ├── orchestrator.py
│   ├── shell_agent.py
│   ├── offline_shell_parser.py
│   ├── safety.py
│   ├── tool_agent.py
│   ├── memory_agent.py
│   ├── process_manager.py
│   ├── llm_client.py
│   ├── config.py
│   ├── schema_protocol.py
│   ├── schema_validator.py
│   ├── llm_debug_log.py
│   ├── a2a/
│   │   ├── models.py
│   │   ├── transport.py
│   │   ├── agents.py
│   │   ├── runtime.py
│   │   └── echo_agent.py
│   └── tools/
│       ├── registry.py
│       ├── file_tools.py
│       ├── system_tools.py
│       ├── network_tools.py
│       ├── mcp_adaptor.py
│       └── mcp_client.py
└── tests/
```

## 10. 已知限制与后续建议

- 直接 shell 模式绕过安全检查，可考虑统一接入 `safety.check_command`
- `ASK` 权限尚未实现真正的人机确认闭环
- `requirements.txt` 中 `a2a-sdk` 目前未在主流程中直接使用
- Windows 平台下某些 shell 语义与 Linux/macOS 命令存在差异，建议增加平台化测试

---

如果你要基于本项目继续开发，建议优先阅读：

1. `src/tui.py`（请求入口与路由）
2. `src/orchestrator.py`（意图分类）
3. `src/shell_agent.py` / `src/tool_agent.py`（执行链路）
4. `src/a2a/runtime.py`（统一门面）
5. `AGENTS.md`（Agent 架构说明）
