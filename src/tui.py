"""Task 1.1: TUI application using Textual framework."""

from __future__ import annotations

import asyncio
import os
import time
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Input, RichLog, Static, OptionList

from textual.binding import Binding
from textual.events import Key
from rich.text import Text
from rich.markdown import Markdown
from rich.panel import Panel

from . import process_manager
from . import llm_client
from .a2a import A2ARuntime
from .memory_agent import save_memory, search_memory
from .tools import file_tools, system_tools, network_tools


# Task 3.3: Common commands for Tab auto-completion
COMPLETION_COMMANDS = [
    # Direct shell commands (/ prefix)
    "/ls", "/ls -la", "/ls -R",
    "/pwd", "/cd", "/cat", "/head", "/tail",
    "/grep", "/find", "/wc", "/echo",
    "/git status", "/git log", "/git diff", "/git branch",
    "/pip install", "/pip list", "/python",
    "/ping", "/curl", "/wget",
    "/mkdir", "/rm", "/mv", "/cp", "/chmod",
    "/ps aux", "/top", "/df -h", "/du -sh",
    "/date", "/whoami", "/uname -a",
    # Natural language shortcuts
    "list files", "show files", "list all python files",
    "find python files", "count lines",
    "system info", "disk usage",
    "current directory", "what time is it",
    "git status", "git log", "git diff",
    "!memory save", "!memory search",
]


class StatusBar(Static):
    """Bottom status bar showing current state."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._agent = "Orchestrator"
        self._status = "Ready"
        self._update_text()

    def _update_text(self):
        cwd = os.getcwd()
        t = time.strftime("%H:%M:%S")
        self.update(f" 🕐 {t}  |  📂 {cwd}  |  🤖 {self._agent}  |  {self._status}")

    def set_agent(self, name: str):
        self._agent = name
        self._update_text()

    def set_status(self, status: str):
        self._status = status
        self._update_text()


class AgentCLI(App):
    """Multi-Agent CLI TUI Application."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #output-area {
        height: 1fr;
        border: solid $primary;
        overflow-y: auto;
    }
    #status-bar {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
    }
    #input-area {
        height: 3;
        dock: bottom;
    }
    Input {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True, priority=True),
        Binding("ctrl+l", "clear_output", "Clear", show=True),
    ]

    TITLE = "Multi-Agent CLI"

    def __init__(self):
        super().__init__()
        self.conversation_history: list[dict] = []
        self._current_task: asyncio.Task | None = None
        self._a2a_runtime = A2ARuntime()
        # Task 3.3 / 进阶: Command history
        self._command_history: list[str] = []
        self._history_index: int = -1
        # Task 3.3: Tab completion state
        self._tab_candidates: list[str] = []
        self._tab_index: int = -1

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="output-area", highlight=True, markup=True, wrap=True)
        yield StatusBar(id="status-bar")
        yield Input(placeholder="Type a command or ask a question... (prefix / for direct shell)", id="input-area")
        yield Footer()
        yield Container(id="interaction-container")

    def on_mount(self):
        # Register all MCP tools
        file_tools.register_all()
        system_tools.register_all()
        network_tools.register_all()

        #输入焦点对准input
        input_widget=self.query_one("#input-area")
        input_widget.focus()

        output = self.query_one("#output-area", RichLog)
        output.write(Panel(
            "[bold cyan]Welcome to Multi-Agent CLI![/]\n\n"
            "• Type natural language to interact with AI agents\n"
            "• Prefix [bold green]/[/] for direct shell commands (e.g. [green]/ls -la[/])\n"
            "• [bold]Tab[/] for auto-completion, [bold]Up/Down[/] for command history\n"
            "• [bold]Ctrl+C[/] to quit, [bold]Ctrl+L[/] to clear\n\n"
            "[dim]Agents: Orchestrator → Shell Agent | Tool Agent | Memory Agent[/]\n"
            "[dim]A2A Mode: on[/]",
            title="ACEE-Multi-Agent CLI",
            border_style="cyan",
        ))
        self._update_status_time()

    def _update_status_time(self):
        """Periodically update the status bar time."""
        try:
            sb = self.query_one("#status-bar", StatusBar)
            sb._update_text()
            self.set_timer(1, self._update_status_time)
        except Exception:
            pass

    def on_key(self, event: Key):
        """Handle key events for command history (Up/Down) and Tab completion."""
        if event.key == "escape":
            self._close_clarification_panel_sync(event)
            return

        input_widget = self.query_one("#input-area", Input)

        if event.key == "up":
            # Navigate command history backwards
            if self._command_history:
                if self._history_index < len(self._command_history) - 1:
                    self._history_index += 1
                input_widget.value = self._command_history[-(self._history_index + 1)]
                input_widget.cursor_position = len(input_widget.value)
            event.prevent_default()
            event.stop()
            return

        if event.key == "down":
            # Navigate command history forwards
            if self._history_index > 0:
                self._history_index -= 1
                input_widget.value = self._command_history[-(self._history_index + 1)]
                input_widget.cursor_position = len(input_widget.value)
            elif self._history_index == 0:
                self._history_index = -1
                input_widget.value = ""
            event.prevent_default()
            event.stop()
            return

        if event.key == "tab":
            # Task 3.3: Tab auto-completion
            current = input_widget.value
            if not current:
                return

            if self._tab_index == -1 or not self._tab_candidates:
                # Build candidate list
                self._tab_candidates = [
                    c for c in COMPLETION_COMMANDS
                    if c.lower().startswith(current.lower())
                ]
                # Also add matching files from cwd
                try:
                    for entry in os.listdir(".")[:50]:
                        if entry.lower().startswith(current.lstrip("/").lower()):
                            prefix = "/" if current.startswith("/") else ""
                            self._tab_candidates.append(prefix + entry)
                except Exception:
                    pass
                self._tab_index = 0
            else:
                self._tab_index = (self._tab_index + 1) % max(len(self._tab_candidates), 1)

            if self._tab_candidates:
                input_widget.value = self._tab_candidates[self._tab_index]
                input_widget.cursor_position = len(input_widget.value)
            event.prevent_default()
            event.stop()
            return

        # Reset tab state on any other key
        self._tab_candidates = []
        self._tab_index = -1

    @on(Input.Submitted)
    async def on_input_submitted(self, event: Input.Submitted):
        user_input = event.value.strip()
        if not user_input:
            return

        input_widget = self.query_one("#input-area", Input)
        input_widget.value = ""

        # Add to command history (进阶: 命令历史记录)
        if not self._command_history or self._command_history[-1] != user_input:
            self._command_history.append(user_input)
        self._history_index = -1
        self._tab_candidates = []
        self._tab_index = -1

        output = self.query_one("#output-area", RichLog)
        output.write(Text(f"\n❯ {user_input}", style="bold green"))

        # Cancel any running task
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        # Check for direct shell command (/ prefix)
        if user_input.startswith("/"):
            cmd = user_input[1:].strip()
            if cmd:
                self._handle_shell_direct(cmd)
            return

        # Check for memory commands
        if user_input.lower().startswith("!memory"):
            parts = user_input.split(maxsplit=2)
            if len(parts) >= 3 and parts[1] == "save":
                result = save_memory(parts[2])
                output.write(Text(f"💾 {result}", style="dim"))
            elif len(parts) >= 3 and parts[1] == "search":
                results = search_memory(parts[2])
                if results:
                    for m in results:
                        output.write(Text(f"  [{m['timestamp']}] {m['content']}", style="dim"))
                else:
                    output.write(Text("  No memories found.", style="dim"))
            else:
                output.write(Text("  Usage: !memory save <text> | !memory search <query>", style="dim"))
            return

        # Route through orchestrator
        self._handle_orchestrated(user_input)

    @work(thread=False)
    async def _handle_shell_direct(self, command: str):
        """Direct shell execution (/ prefix) — Task 1.2."""
        output = self.query_one("#output-area", RichLog)
        sb = self.query_one("#status-bar", StatusBar)

        sb.set_agent("Shell (direct)")
        sb.set_status("Running...")
        output.write(Text(f"$ {command}", style="bold yellow"))

        async def on_output(text: str):
            output.write(Text(text.rstrip("\n"), style="white"))

        async def on_done(code: int):
            color = "green" if code == 0 else "red"
            output.write(Text(f"[exit code: {code}]", style=color))

        await process_manager.run_command(command, on_output, on_done)
        sb.set_agent("Orchestrator")
        sb.set_status("Ready")
    


    @work(thread=False)
    async def _handle_orchestrated(self, user_input: str):
        """Full orchestrator pipeline — Task 2.3."""
        output = self.query_one("#output-area", RichLog)
        sb = self.query_one("#status-bar", StatusBar)

        sb.set_agent("Orchestrator")
        sb.set_status("Analyzing intent...")

        # Get memory context
        mem_ctx = await self._get_memory_context(user_input)
        if mem_ctx:
            output.write(Text(mem_ctx, style="dim italic"))

        # Classify intent
        classification = await self._classify_intent(user_input)
        intent = classification.get("intent", "direct_answer")
        reasoning = classification.get("reasoning", "")
        confidence = classification.get("confidence", 0)

        output.write(Text(
            f"[Orchestrator] Intent: {intent} (confidence: {confidence:.0%}) — {reasoning}",
            style="dim cyan",
        ))

        self.conversation_history.append({"role": "user", "content": user_input})

        if intent == "shell_agent":
            await self._dispatch_shell(user_input, classification, output, sb)
        elif intent == "tool_agent": #大多数命令行都会被判定为tool_agent，所以可能看不到命令执行提示。
            await self._dispatch_tool(user_input, classification, output, sb)
            #await self._dispatch_shell(user_input, classification, output, sb)
        elif intent == "clarification":
            # 强制改为 shell_agent 意图
            intent = "shell_agent"
            # 保留原始的用户输入作为任务描述
            classification["task_description"] = user_input
            await self._dispatch_shell(user_input, classification, output, sb)
        else:
            # direct_answer
            msg = classification.get("message", "")
            if msg:
                output.write(Text(f"💬 {msg}", style="white"))
                self.conversation_history.append({"role": "assistant", "content": msg})
            else:
                # Fallback: stream a response
                sb.set_status("Generating response...")
                messages = [
                    {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
                    {"role": "user", "content": user_input},
                ]
                full_resp = []
                async for chunk in llm_client.chat(messages):
                    full_resp.append(chunk)
                resp_text = "".join(full_resp)
                try:
                    output.write(Markdown(resp_text))
                except Exception:
                    output.write(Text(resp_text))
                self.conversation_history.append({"role": "assistant", "content": resp_text})

        sb.set_agent("Orchestrator")
        sb.set_status("Ready")

    async def _get_memory_context(self, user_input: str) -> str:
        return await self._a2a_runtime.get_relevant_context(user_input)

    async def _classify_intent(self, user_input: str) -> dict:
        return await self._a2a_runtime.classify_intent(
            user_input, self.conversation_history
        )

    async def _dispatch_shell(self, user_input, classification, output, sb):
        """Dispatch to Shell Agent — Task 3."""
        sb.set_agent("Shell Agent")
        sb.set_status("Generating command...")

        task_desc = classification.get("task_description", user_input)
        result = await self._a2a_runtime.generate_command(task_desc, user_input)

        intent = result.get("intent", "refuse")
        command = result.get("command", "")
        reason = result.get("reason", "")
        risk = result.get("risk_level", "unknown")
        safety = result.get("safety_check", {})
        

        if intent == "refuse" or safety.get("level") == "deny":
            output.write(Panel(
                f"[bold red]BLOCKED[/]\n"
                f"Command: [yellow]{command}[/]\n"
                f"intent: {intent}\n"
                f"Reason: {reason}\n"
                f"Safety: {'; '.join(safety.get('reasons', []))}",
                title="🛡️ Safety Block",
                border_style="red",
            ))
            self.conversation_history.append({
                "role": "assistant",
                "content": f"[Refused] {reason}",
            })
            return

        if intent == "ask_clarification": # 缺乏循环边界检测
            options = result.get("clarification_options", [])
            message = classification.get("message", "Could you clarify what you mean?")
            await self._show_clarification_panel(message, options)
            return

        # Show command info
        risk_level = result.get("risk_level", "unknown")
        risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(risk_level, "white")
        warn_reasons = safety.get("reasons", [])

        # If safety level is "warn", upgrade risk level to "medium"
        if safety.get("level") == "warn":
            risk_level = "medium"

        if risk_level in ("medium", "high"):
            output.write(Panel(
                f"Command: [bold]{command}[/]\n"
                f"Reason: {reason}\n"
                f"intent: {intent}\n"
                f"Risk: [{risk_color}]{risk_level}[/]\n"
                f"Warnings: {'; '.join(warn_reasons) if warn_reasons else 'none'}",
                title="⚠️ Command Requires Caution",
                border_style="yellow",
            ))
        else:
            output.write(Panel(
                f"Command: [bold]{command}[/]\n"
                f"Reason: {reason}\n"
                f"intent: {intent}\n"
                f"Risk: [{risk_color}]{risk}[/]\n"
                f"Warnings: {'; '.join(warn_reasons) if warn_reasons else 'none'}",
                title="✔ Command Safely conducted",
                border_style="green",
            ))  

        # Execute
        sb.set_status(f"Running: {command[:40]}...")
        output.write(Text(f"$ {command}", style="bold yellow"))

        full_output = []

        async def on_line(text: str):
            full_output.append(text)
            output.write(Text(text.rstrip("\n"), style="white"))

        async def on_done(code: int):
            color = "green" if code == 0 else "red"
            output.write(Text(f"[exit code: {code}]", style=color))

        await process_manager.run_command(command, on_line, on_done)
        self.conversation_history.append({
            "role": "assistant",
            "content": f"Executed: {command}\nOutput: {''.join(full_output)[:500]}",
        })

    async def _dispatch_tool(self, user_input, classification, output, sb):
        """Dispatch to Tool Agent — Task 4."""
        sb.set_agent("Tool Agent")
        sb.set_status("Using tools...")

        task_desc = classification.get("task_description", user_input)

        async def on_tool_output(text: str):
            output.write(Text(text.rstrip("\n"), style="dim white"))

        result = await self._a2a_runtime.handle_tool_task(task_desc, user_input, on_tool_output)
        if result:
            try:
                output.write(Markdown(result))
            except Exception:
                output.write(Text(result))
        self.conversation_history.append({"role": "assistant", "content": result or ""})

    def action_clear_output(self):
        output = self.query_one("#output-area", RichLog)
        output.clear()

    def action_quit(self):
        self.exit()

    async def _show_clarification_panel(self, question: str, options: list):
        output = self.query_one("#output-area", RichLog)
        interaction_container = self.query_one("#interaction-container", Container)

        # 1. 渲染问题到日志区
        output.write(Text(f"❓ {question}", style="yellow bold"))

        # 2. 如果没有选项，直接返回
        if not options:
            return

        # 3. 【关键修复】：在添加新组件前，先尝试移除旧的 OptionList
        # 防止 ID 重复报错
        try:
            old_list = self.query_one("#clarification-list", OptionList)
            await old_list.remove()
        except Exception:
            pass  # 如果找不到旧组件，说明是第一次，忽略错误

        # 4. 创建新的 OptionList 组件
        clarification_list = OptionList(*options, id="clarification-list")

        # 5. 【关键逻辑】：将组件添加到 Container 中（而不是直接加到 Log 里）
        await interaction_container.mount(clarification_list)

        # 6. 【关键修复】：等待组件渲染完成后再聚焦
        await asyncio.sleep(0.1)
        clarification_list.focus()
    
    async def on_option_list_option_selected(self, event: OptionList.OptionSelected):

        if event.option_list.id == "clarification-list":
            # 1. 获取用户选择的值
            selected_value = event.option.prompt

            # 2. 从界面上移除这个交互组件，保持界面整洁
            await event.option_list.remove()

            # 3. 将选中的值作为用户的"新输入"进行处理
            # 这会触发新一轮的 _handle_orchestrated 循环
            # @work 装饰器会处理异步执行，无需 await
            self._handle_orchestrated(f"Selected: {selected_value}")


    def _close_clarification_panel_sync(self, event: Key) -> None:
        """Close clarification panel on ESC without defining a duplicate on_key handler."""
        try:
            clarification_list = self.query_one("#clarification-list", OptionList)
            if self.focused == clarification_list or self.query_one("#interaction-container").query(OptionList):
                self.call_later(self._close_clarification_panel)
                event.stop()
        except Exception:
            pass

    async def _close_clarification_panel(self) -> None:
        """关闭澄清面板（移除 OptionList）"""
        try:
            # 查询并移除 OptionList
            clarification_list = self.query_one("#clarification-list", OptionList)
            await clarification_list.remove()
            # 在日志区输出一条消息，告知用户已取消
            output = self.query_one("#output-area", RichLog)
            output.write(Text("🚫 澄清面板已关闭", style="dim yellow"))
        except Exception:
            # 如果没有找到 OptionList，说明面板已经关闭或不存在，忽略错误
            pass