# agent.md

本文件为 ACEE 项目的 Agent 说明入口，便于按你指定的文件名快速查看。

完整版本请阅读：`AGENTS.md`

## 快速摘要

- ACEE 采用多 Agent 架构：Orchestrator、Shell、Tool、Memory
- 通过 A2A Runtime 统一封装内部调用与状态返回
- Shell 支持 `llm | auto | offline` 三模式
- Tool Agent 采用 function-calling + ReAct 循环
- Safety 使用本地规则引擎（`safe/warn/deny`）
- 记忆持久化于 `memory.json`，支持启动注入和检索

## 文档导航

- 项目总览与使用：`README.md`
- Agent 全量架构说明：`AGENTS.md`
