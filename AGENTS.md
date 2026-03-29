# ACEE Agent 架构与运行指南

本文档面向开发者，完整说明 ACEE 的 Agent 设计、执行链路、协议封装、权限与风险边界。

## 1. 设计目标

ACEE 的 Agent 系统围绕三个目标构建：

1. 路由准确：根据用户输入在 shell、tool、direct_answer、clarification 间做稳定分发。
2. 执行可控：在命令和工具执行链路中提供风险分层与权限约束。
3. 扩展友好：通过 A2A 统一封装对内调用接口，便于新增 Agent 或替换底层实现。

## 2. 分层模型

系统可以按四层理解：

1. 交互层（Interaction Layer）
- `src/tui.py`（Textual App）
- 输入解析、状态展示、流式输出、快捷键、澄清面板

2. 决策层（Decision Layer）
- `src/orchestrator.py`
- 意图分类、上下文注入、离线预分类

3. 执行层（Execution Layer）
- `src/shell_agent.py`
- `src/tool_agent.py`
- `src/process_manager.py`

4. 治理层（Governance Layer）
- `src/safety.py`（命令风险规则）
- `src/tools/registry.py`（工具权限）
- `src/memory_agent.py`（记忆）
- `src/a2a/*`（协议与传输）

## 3. 启动与注册流程

启动入口：`run.py`

真实流程：

1. `run.py` 导入并调用 `src/main.py:main()`。
2. `main()` 加载 `.env`，创建全局 `MCPAdapter`。
3. `main()` 调用 `tool_agent.set_mcp_adapter(...)` 注入 MCP 能力。
4. 若 `MCP_SERVERS` 配置非空，`main()` 给 TUI 注入异步 MCP 初始化钩子。
5. `AgentCLI.run()` 启动，`on_mount` 中注册本地 file/system/network tools。
6. `A2ARuntime` 在 `AgentCLI.__init__` 中创建并注册 orchestrator/shell/tool/memory/echo adapters。

## 4. 输入模式与分发优先级

在 `src/tui.py` 的 `on_input_submitted` 中，输入按以下顺序处理：

1. `/help` 本地帮助
- 不调用 Orchestrator
- 直接在 UI 渲染帮助文档

2. `/` 前缀直接命令
- 调用 `process_manager.run_command`
- 不经过 Shell Agent
- 不经过 Safety

3. `!memory` 命令
- `!memory save <text>` 保存记忆
- `!memory search <query>` 查询记忆

4. 默认自然语言
- 进入 Orchestrator 分类
- 根据 intent 分发 Shell/Tool/Direct Answer

## 5. Orchestrator Agent

文件：`src/orchestrator.py`

### 5.1 意图空间

`intent` 枚举：
- `shell_agent`
- `tool_agent`
- `direct_answer`
- `clarification`

### 5.2 输出契约

通过 JSON Schema 校验后返回：
- `intent`
- `reasoning`
- `confidence`（0~1）
- `message`
- `task_description`

### 5.3 关键机制

1. 上下文注入
- OS、shell、cwd、目录快照、git 状态、环境变量摘要
- `context_signals` 包含 repo_tags、directory_risk 等信号

2. 离线优先分类
- 开关：`ACEE_ORCH_OFFLINE_FIRST`（默认开）
- 先走 `offline_shell_parser.generate_command_offline`
- 若命中且不允许 fallback，可直接返回分类结果，跳过 LLM

3. 失败兜底
- LLM/Schema 失败时回退到 `clarification` 或保守回答

## 6. Shell Agent

文件：`src/shell_agent.py`

### 6.1 输入输出

输入：`task_description + user_input + history`

输出字段：
- `intent`: `run_command | ask_clarification | refuse`
- `command`
- `reason`
- `risk_level`
- `clarification_options`
- `safety_check`

### 6.2 三种模式

通过 `ACEE_SHELL_MODE` 控制：

1. `llm`（默认）
- 直接调用 LLM 生成命令

2. `auto`
- 先离线解析
- 离线不确定时允许回退到 LLM

3. `offline`
- 只允许离线解析
- 无可执行结果时返回拒绝

### 6.3 澄清交互

当返回 `ask_clarification`：
- TUI 挂载 `OptionList` 面板
- 用户选择后以新输入再次进入编排流程

## 7. Offline Shell Parser

文件：`src/offline_shell_parser.py`

能力：
- 基于 regex + 可选 `jieba` 分词
- 识别操作意图（list/search/read/delete/move/kill/system info 等）
- 提取 path/ext/pid 等参数
- 生成跨平台命令模板（Windows/Unix）
- 输出 `risk_score` 和 `risk_reasons`

注意：
- `jieba` 为可选依赖，缺失时使用回退分词方案。

## 8. Safety Engine

文件：`src/safety.py`

规则分层：

1. `DENY_PATTERNS`
- `rm -rf`、`mkfs`、`dd if=`、`shutdown`、`reboot`、危险 SQL 等
- 命中则直接 `deny`

2. `WARN_PATTERNS`
- `sudo`、`git push --force`、`git reset --hard`、`curl|sh` 等
- 命中则 `warn`

返回：
- `{"level": "safe|warn|deny", "reasons": [...]}`

风险边界：
- 直接 shell（`/` 前缀）不经过该引擎。

## 9. Tool Agent

文件：`src/tool_agent.py`

### 9.1 循环机制

实现 ReAct 风格循环，最多 5 轮：

1. LLM 选择工具（function calling）
2. 执行工具，回填 tool message
3. 继续让 LLM 决定下一步
4. 无工具调用时输出最终结果

### 9.2 权限策略

从 `src/tools/registry.py` 读取权限：
- `ALLOW`
- `ASK`
- `DENY`

当前实现细节：
- `DENY` 会拦截
- `ASK` 仅提示警告后自动放行（尚未实现真正用户确认）

### 9.3 MCP 工具

当工具名包含 `__` 且 MCP 适配器存在时，转到 MCP 执行路径。

## 10. Tool Registry 与本地工具

目录：`src/tools/`

1. `registry.py`
- 工具注册、列举、执行、权限查询

2. `file_tools.py`
- `read_file`, `write_file`, `list_directory`, `file_exists`, `search_files`, `count_lines`

3. `system_tools.py`
- `get_system_info`, `get_disk_usage`, `get_env_var`

4. `network_tools.py`
- `fetch_url`, `call_rest_api`

5. `mcp_adaptor.py`
- 启动 MCP server 子进程
- 拉取 MCP 工具列表并转换为 OpenAI tool schema
- 执行 MCP tools/call

## 11. Memory Agent

文件：`src/memory_agent.py`

存储：`memory.json`

关键能力：

1. 保存
- `save_memory_record` 持久化记录（包含 tags、metadata、timestamp）
- 支持 `auto_tag`，会根据本地规则推断标签

2. 检索
- `search_memory(query)` 按内容与标签评分
- `get_relevant_context(user_input)` 返回 top-k 相关记忆文本

3. 启动注入
- `get_startup_context(limit)` 结合标签权重和时间衰减排序
- TUI 启动后将高相关记忆注入会话

## 12. A2A 协议与运行时

目录：`src/a2a/`

### 12.1 协议模型

- `A2ARequest`
- `A2AResponse`
- `TaskState`
- `ErrorEnvelope`

### 12.2 传输层

`InProcessTransport.send(request)`：
- 根据 `to_agent` 查找 handler
- 捕获可恢复异常并返回标准失败响应
- 维护 state history

### 12.3 Runtime 门面

`A2ARuntime` 封装对外方法：
- `classify_intent`
- `generate_command`
- `handle_tool_task`
- `get_relevant_context`
- `get_startup_context`
- `save_auto_memory`
- `test_echo`

## 13. 配置项（影响 Agent 行为）

LLM 相关：
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_TEMPERATURE_STREAM`
- `OPENAI_TEMPERATURE_JSON`
- `OPENAI_TEMPERATURE_TOOL`
- `OPENAI_JSON_RETRY_COUNT`

Agent 行为：
- `ACEE_SHELL_MODE`
- `ACEE_ORCH_OFFLINE_FIRST`
- `ACEE_TAG_FALLBACK_MODE`
- `ACEE_LLM_DEBUG_LOG`
- `ACEE_LLM_DEBUG_LOG_PATH`
- `MCP_SERVERS`

## 14. 测试覆盖

`tests/` 当前覆盖点：
- Orchestrator 离线优先与上下文注入
- A2A 历史消息透传
- Shell/Tool prompt 历史清洗
- Echo Agent 协议连通
- MCP 连接脚本

仍可加强：
- TUI 交互端到端测试
- direct shell 风险治理策略测试
- Tool Agent ASK 的人工确认闭环测试

## 15. 已知问题与技术债

1. direct shell (`/`) 绕过 Safety。
2. Tool Agent 的 `ASK` 当前自动放行。
3. `requirements.txt` 包含 `a2a-sdk`，但主流程未直接使用。
4. MCP 适配层在不同平台下的子进程通信稳定性仍需持续验证。

## 16. 扩展建议

### 16.1 新增 Agent

1. 在 `src/` 实现业务逻辑
2. 在 `src/a2a/agents.py` 增加 Adapter 与 capabilities
3. 在 `src/a2a/runtime.py` 注册并暴露门面方法
4. 在 `src/orchestrator.py` 扩展 intent 和路由提示
5. 在 `src/tui.py` 接入分发分支

### 16.2 新增 Tool

1. 在 `src/tools/*.py` 新增异步 handler
2. 在 `register_all()` 注册 schema 与权限
3. 确认 Tool Agent 能通过 function-calling 发现并调用

### 16.3 强化安全治理

1. 扩展 `DENY_PATTERNS` 与 `WARN_PATTERNS`
2. 给 direct shell 路径加入预检查
3. 对 `ASK` 实现阻塞式用户确认
