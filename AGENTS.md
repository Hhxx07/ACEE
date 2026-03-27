# ACEE Agent Guide

## 1. 目标

本文档专门解释 ACEE 项目中的 agent 体系如何协作，重点是：

1. 每个 agent 负责什么。
2. 请求如何在 agent 之间流转。
3. A2A 模式开启后调用链如何变化。
4. 新增 agent 的最小接入步骤。

## 2. Agent 列表

### 2.1 Orchestrator Agent

文件：[src/orchestrator.py](src/orchestrator.py)

职责：

1. 理解用户输入意图。
2. 决定路由到 `shell_agent`、`tool_agent`、`direct_answer`、`clarification`。
3. 输出结构化决策 JSON（含 `intent`、`confidence`、`task_description` 等）。

### 2.2 Shell Agent

文件：[src/shell_agent.py](src/shell_agent.py)

职责：

1. 将自然语言任务转成 shell 命令。
2. 根据 `ACEE_SHELL_MODE` 决定离线解析或 LLM 解析。
3. 对命令执行本地安全后检查（`safety.check_command`）。

### 2.3 Tool Agent

文件：[src/tool_agent.py](src/tool_agent.py)

职责：

1. 使用 function-calling 进行工具选择和调用。
2. 通过 ReAct 循环完成多步任务。
3. 执行工具权限策略（ALLOW/ASK/DENY）。

### 2.4 Memory Agent

文件：[src/memory_agent.py](src/memory_agent.py)

职责：

1. 持久化保存记忆到 `memory.json`。
2. 按关键词检索历史信息。
3. 为当前对话提供相关上下文提示。

### 2.5 Safety Engine（辅助模块）

文件：[src/safety.py](src/safety.py)

职责：

1. 对高危命令进行阻断（deny）。
2. 对中风险命令进行警告（warn）。
3. 返回统一风险等级和原因列表。

## 3. Agent 协作链路

默认自然语言链路（非 `/` 直接命令）：

1. TUI 收到用户输入（[src/tui.py](src/tui.py)）。
2. 读取记忆上下文（memory）。
3. Orchestrator 分类意图。
4. 路由到 Shell Agent 或 Tool Agent。
5. Shell 路径：生成命令 -> 安全检查 -> 进程执行。
6. Tool 路径：ReAct 循环调用工具 -> 汇总输出。
7. 结果写回 TUI，并追加会话历史。

直接命令链路（`/xxx`）：

1. TUI 直接调用 [src/process_manager.py](src/process_manager.py) 执行。
2. 不经过 Orchestrator / Shell Agent / Safety Engine。

## 4. A2A 模式下的变化

A2A 相关文件：

1. [src/a2a/models.py](src/a2a/models.py)
2. [src/a2a/transport.py](src/a2a/transport.py)
3. [src/a2a/agents.py](src/a2a/agents.py)
4. [src/a2a/runtime.py](src/a2a/runtime.py)

当 `ACEE_A2A_MODE != off` 时：

1. TUI 不直接调用各 agent 函数。
2. TUI 调用 `A2ARuntime`。
3. Runtime 封装 `A2ARequest` 发给 `InProcessTransport`。
4. Transport 根据 `to_agent` 分发到 adapter。
5. adapter 调用原有业务函数并返回 `A2AResponse`。

当前模式说明：

1. `off`：旧链路。
2. `on`：A2A 链路。
3. `shadow`：目前行为与 `on` 一致（尚未做双链路 diff）。

## 5. 环境变量（与 Agent 行为直接相关）

1. `ACEE_A2A_MODE=off|shadow|on`
2. `ACEE_SHELL_MODE=auto|offline|llm`
3. `OPENAI_API_KEY`
4. `OPENAI_BASE_URL`
5. `OPENAI_MODEL`

## 6. 新增 Agent 的最小步骤

如果要新增一个 `planner_agent`，建议按以下最小路径接入：

1. 在 `src/` 下实现核心业务函数（例如 `planner_agent.py`）。
2. 在 [src/a2a/agents.py](src/a2a/agents.py) 增加对应 adapter 类和 capability。
3. 在 [src/a2a/runtime.py](src/a2a/runtime.py) 注册 adapter 并提供 facade 方法。
4. 在 [src/tui.py](src/tui.py) 的 orchestrated 路由中接入新 intent 分支。
5. 在 [src/orchestrator.py](src/orchestrator.py) 的提示词和意图枚举中加入新 intent。

## 7. 风险边界和实现注意点

1. `/` 直接命令当前不走安全引擎，属于高权限快路径。
2. Tool `ASK` 权限目前会提示后自动放行，若要严格化需加确认交互。
3. A2A 已有统一错误模型（`ErrorEnvelope`）和任务状态，但尚未实现完整 shadow 对比。
4. `tests/` 目录当前为空，建议尽快增加路由与安全回归测试。

## 8. 快速理解这套 Agent 系统

可以把 ACEE 理解为四层：

1. 交互层：TUI 接收与展示。
2. 决策层：Orchestrator 进行意图路由。
3. 执行层：Shell Agent / Tool Agent / Process Manager。
4. 治理层：Safety、Permission、Memory、A2A 协议封装。

这让项目既能快速响应用户输入，也保留了后续向跨进程 agent 架构演进的空间。
