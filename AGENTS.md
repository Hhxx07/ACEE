# ACEE Agent 系统与架构详细指南

## 1. 项目目标与简介

ACEE 是一个基于终端（Terminal-based）的多 Agent 系统。该系统的核心目标是接收自然语言输入，决策用户意图，将任务分发给专有的 Agent 进行处理，执行动作，并将结果流式返回给用户。

本项目不仅旨在作为一个可用的 CLI 助手，还保留了通过适配器（Adapters）和进程内传输（In-process transport）向跨进程 Agent-to-Agent (A2A) 架构演进的空间。

## 2. 核心架构与心智模型

为了快速理解 ACEE 的 Agent 系统，可以将其划分为以下四个核心层级：

1. **交互层 (Interaction Layer)**：TUI（Textual UI）负责接收用户输入与展示流式输出。
2. **决策层 (Decision Layer)**：Orchestrator Agent 负责理解上下文并进行意图路由。
3. **执行层 (Execution Layer)**：Shell Agent / Tool Agent / Process Manager 负责具体任务的执行与工具调用。
4. **治理层 (Governance Layer)**：涵盖 Safety（安全）、Permission（权限）、Memory（记忆）以及 A2A 协议封装。

## 3. 启动流程与入口

程序的执行入口为项目根目录的 `run.py`：
1. 将项目根目录添加至 `sys.path`。
2. 从 `src/main.py` 导入并执行 `main()`。
3. 加载项目根目录下的 `.env` 环境变量。
4. 创建并启动基于 Textual 的 `AgentCLI` TUI 应用。

**启动命令**：
```bash
python run.py
```

## 4. 核心 Agent 与模块详解

### 4.1 Orchestrator Agent (编排代理)
* **文件**：`src/orchestrator.py`
* **职责**：
    1. 注入操作系统、当前工作目录（cwd）等上下文信息。
    2. 理解用户的自然语言输入意图。
    3. 决定路由到 `shell_agent`、`tool_agent`、`direct_answer` 还是 `clarification`。
    4. 输出结构化的决策 JSON（包含 `intent`、`reasoning`、`confidence`、`task_description` 等字段）。

### 4.2 Shell Agent (终端代理)
* **文件**：`src/shell_agent.py`
* **职责**：
    1. 将自然语言任务转换为 shell 命令的 JSON 格式。
    2. 根据环境变量 `ACEE_SHELL_MODE` 决定使用离线解析引擎还是 LLM 直接解析。
    3. 在命令执行前，调用 `safety.check_command` 进行本地安全后检查。

### 4.3 Offline Shell Parser (离线 Shell 解析器)
* **文件**：`src/offline_shell_parser.py`
* **职责**：
    1. 基于规则的意图检测引擎。
    2. 支持通过 `jieba`（如果可用）进行中文分词。
    3. 提取路径、扩展名、PID 等关键参数。
    4. 评估风险得分并生成原因，针对不同操作系统生成对应的命令模板。

### 4.4 Tool Agent (工具代理)
* **文件**：`src/tool_agent.py`
* **职责**：
    1. 采用 ReAct（Reasoning and Acting）风格的循环处理多步任务，并设有最大迭代次数限制。
    2. 使用 LLM 的 Function-Calling 功能进行工具选择。
    3. 通过 Tool Registry 执行工具，并将观察结果（observations）追加回消息历史。
    4. 严格执行工具权限策略（ALLOW / ASK / DENY）。

### 4.5 Memory Agent (记忆代理)
* **文件**：`src/memory_agent.py`
* **职责**：
    1. 将记忆条目持久化保存到项目根目录的 `memory.json`。
    2. 基于关键词打分机制检索历史信息。
    3. 为当前的对话输入提供高度相关的上下文提示。

### 4.6 辅助及底层模块
* **LLM Client (`src/llm_client.py`)**：提供标准对话、流式输出、JSON 强制输出（带重试机制）以及 OpenAI 风格的函数调用封装。
* **Safety Engine (`src/safety.py`)**：包含 `DENY_PATTERNS`（硬性拦截）和 `WARN_PATTERNS`（警告）。返回统一的风险等级（`safe`|`warn`|`deny`）和原因列表。
* **Tool Registry (`src/tools/registry.py`)**：管理工具注册、供 LLM 使用的 Schema 列表、权限查找以及执行分发。内置了文件、系统、网络等工具集。
* **Process Manager (`src/process_manager.py`)**：提供异步子进程执行，支持流式 stdout/stderr 回调与完成状态回调。

## 5. Agent 协作与运行链路

用户在 TUI 提交输入后，请求会进入以下三种模式之一：

### 5.1 默认自然语言链路 (Orchestrated NL Mode)
这是最复杂的协作链路，通过 `A2ARuntime` 路由：
1. TUI 接收输入并读取相关的 Memory 上下文。
2. Orchestrator 识别意图。
3. 根据意图分发：
    * **Shell 路径**：生成命令 -> 安全检查 (Safety) -> Process Manager 进程执行。
    * **Tool 路径**：进入 ReAct 循环 -> 调用 Tool Registry 中的工具 -> 汇总输出。
4. 将最终结果渲染至界面，并追加到会话历史。

### 5.2 直接命令链路 (Direct Shell Mode)
* **触发方式**：以 `/` 开头的输入（例如 `/ls -la`）。
* **链路**：TUI 直接调用 Process Manager 异步执行并流式输出。
* **注意**：此模式属于高权限快路径，**不经过** Orchestrator、Shell Agent 或 Safety Engine 安全检查。

### 5.3 记忆命令链路 (Memory Command Mode)
* **触发方式**：使用 `!memory` 前缀。
* **支持命令**：`!memory save <text>` 或 `!memory search <query>`。
* **链路**：直接交由 Memory Agent 处理并读写 `memory.json`。

## 6. A2A (Agent-to-Agent) 运行链路

当前实现为进程内（In-process）A2A 架构，相关代码位于 `src/a2a/` 目录下。

**运行机制**：
1. TUI 不再直接调用各 Agent 的底层函数，而是统一调用 `A2ARuntime` 门面（Facade）。
2. Runtime 将请求封装为 `A2ARequest` 发送给 `InProcessTransport`。
3. Transport 根据 `to_agent` 标识将请求分发给对应的 Agent Adapter（例如 orchestrator/shell/tool/memory adapter）。
4. Adapter 调用原有的业务函数，并将结果包装为 `A2AResponse` 返回。
5. A2A 层负责维护统一的任务生命周期状态（`created`, `running`, `waiting`, `completed`, `failed`, `cancelled`）以及标准的错误模型（`ErrorEnvelope`）。

## 7. 环境配置与状态管理

**环境变量 (直接影响 Agent 行为)**：
* `OPENAI_API_KEY`：API 密钥。
* `OPENAI_BASE_URL`：API 基础地址。
* `OPENAI_MODEL`：指定驱动 Agent 的大语言模型。
* `ACEE_SHELL_MODE`：控制 Shell Agent 行为：
    * `auto`：优先尝试离线规则解析，允许回退到 LLM。
    * `offline`：仅使用离线解析，解析失败则拒绝执行。
    * `llm`：跳过离线解析，直接使用 LLM 生成命令。

**状态管理**：
* 持久化状态：`memory.json`。
* 内存状态：TUI 的会话历史、A2A Runtime 实例上下文、Tool Registry 与权限表。

## 8. 风险边界与技术债

1. **安全绕过**：`/` 直接命令目前绕过 Safety Engine，属于潜在的风险缺口。
2. **权限交互待完善**：对于标记为 `ASK` 权限的工具（如网络工具），目前系统会在输出警告后自动放行，若需严格管控，需要增加显式的用户确认交互逻辑。
3. **测试覆盖**：`tests/` 目录目前为空，亟需补充路由决策与安全引擎的回归测试。
4. **依赖未激活**：`requirements.txt` 中包含 `a2a-sdk`，但在当前源码中暂未实际 import，这属于遗留的技术债。

## 9. 扩展指南

### 9.1 新增 Agent 的最小步骤
若要新增一个如 `planner_agent` 的模块，推荐以下接入路径：
1. 在 `src/` 目录下实现核心业务逻辑函数（如 `planner_agent.py`）。
2. 在 `src/a2a/agents.py` 中增加对应的 Adapter 类和 Capability 定义。
3. 在 `src/a2a/runtime.py` 中注册该 Adapter 并提供对外调用的 facade 方法。
4. 在 `src/orchestrator.py` 的提示词与意图枚举中添加新 Agent 对应的 Intent。
5. 在 `src/tui.py` 的 Orchestrated 路由逻辑中增加处理该新 Intent 的分支。

### 9.2 新增 Tool
1. 在 `src/tools/` 目录下（如新建或现有文件中）实现异步的工具处理函数。
2. 在工具集的 `register_all()` 方法中注册工具 Schema 和默认权限。
3. 注册后，Tool Agent 的 Function-Calling 循环即可自动发现并调用该工具。

### 9.3 强化系统安全 (Safety)
1. 在 `src/safety.py` 中扩展 `DENY_PATTERNS` 或 `WARN_PATTERNS` 的正则表达式。
2. （可选）修改 `process_manager` 或直接命令的路由链路，为 `/` 开头的命令强制施加安全检查。
3. 增加对被拦截或高风险命令的日志审计功能。