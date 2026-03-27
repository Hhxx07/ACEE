"""Task 1.1: TUI application using Textual framework."""

from __future__ import annotations

import asyncio
import os
import time
from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Input, RichLog, Static
from textual.binding import Binding
from rich.text import Text
from rich.markdown import Markdown
from rich.panel import Panel

from . import process_manager
from . import orchestrator
from . import shell_agent
from . import tool_agent
from . import llm_client
from .memory_agent import save_memory, search_memory, get_relevant_context
from .tools import file_tools, system_tools, network_tools


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

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="output-area", highlight=True, markup=True, wrap=True)
        yield StatusBar(id="status-bar")
        yield Input(placeholder="Type a command or ask a question... (prefix / for direct shell)", id="input-area")
        yield Footer()

    def on_mount(self):
        # Register all MCP tools
        file_tools.register_all()
        system_tools.register_all()
        network_tools.register_all()

        output = self.query_one("#output-area", RichLog)
        output.write(Panel(
            "[bold cyan]Welcome to Multi-Agent CLI![/]\n\n"
            "• Type natural language to interact with AI agents\n"
            "• Prefix [bold green]/[/] for direct shell commands (e.g. [green]/ls -la[/])\n"
            "• [bold]Ctrl+C[/] to quit, [bold]Ctrl+L[/] to clear\n\n"
            "[dim]Agents: Orchestrator → Shell Agent | Tool Agent[/]",
            title="🚀 Multi-Agent CLI",
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

    @on(Input.Submitted)
    async def on_input_submitted(self, event: Input.Submitted):
        user_input = event.value.strip()
        if not user_input:
            return

        input_widget = self.query_one("#input-area", Input)
        input_widget.value = ""

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
        mem_ctx = get_relevant_context(user_input)
        if mem_ctx:
            output.write(Text(mem_ctx, style="dim italic"))

        # Classify intent
        classification = await orchestrator.classify_intent(
            user_input, self.conversation_history
        )
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
        elif intent == "tool_agent":
            await self._dispatch_tool(user_input, classification, output, sb)
        elif intent == "clarification":
            msg = classification.get("message", "Could you clarify what you mean?")
            output.write(Text(f"❓ {msg}", style="yellow"))
            self.conversation_history.append({"role": "assistant", "content": msg})
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
                async for chunk in llm_client.chat_stream(messages):
                    full_resp.append(chunk)
                resp_text = "".join(full_resp)
                try:
                    output.write(Markdown(resp_text))
                except Exception:
                    output.write(Text(resp_text))
                self.conversation_history.append({"role": "assistant", "content": resp_text})

        sb.set_agent("Orchestrator")
        sb.set_status("Ready")

    async def _dispatch_shell(self, user_input, classification, output, sb):
        """Dispatch to Shell Agent — Task 3."""
        sb.set_agent("Shell Agent")
        sb.set_status("Generating command...")

        task_desc = classification.get("task_description", user_input)
        result = await shell_agent.generate_command(task_desc, user_input)

        intent = result.get("intent", "refuse")
        command = result.get("command", "")
        reason = result.get("reason", "")
        risk = result.get("risk_level", "unknown")
        safety = result.get("safety_check", {})

        if intent == "refuse" or safety.get("level") == "deny":
            output.write(Panel(
                f"[bold red]BLOCKED[/]\n"
                f"Command: [yellow]{command}[/]\n"
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

        if intent == "ask_clarification":
            options = result.get("clarification_options", [])
            msg = f"❓ {reason}\n"
            if options:
                for i, opt in enumerate(options, 1):
                    msg += f"  [{i}] {opt}\n"
            output.write(Text(msg.rstrip(), style="yellow"))
            self.conversation_history.append({"role": "assistant", "content": msg})
            return

        # Show command info
        risk_color = {"low": "green", "medium": "yellow", "high": "red"}.get(risk, "white")
        warn_reasons = safety.get("reasons", [])

        if safety.get("level") == "warn" or risk in ("medium", "high"):
            output.write(Panel(
                f"Command: [bold]{command}[/]\n"
                f"Reason: {reason}\n"
                f"Risk: [{risk_color}]{risk}[/]\n"
                f"Warnings: {'; '.join(warn_reasons) if warn_reasons else 'none'}",
                title="⚠️ Command Requires Caution",
                border_style="yellow",
            ))
        else:
            output.write(Text(
                f"🔧 {reason}\n$ {command}  [risk: {risk}]",
                style="cyan",
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

        result = await tool_agent.handle_task(task_desc, user_input, on_tool_output)
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
