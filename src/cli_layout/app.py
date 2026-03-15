"""Main Textual application for CLI Layout."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Static

from cli_layout.config import load_config, AppConfig
from cli_layout.events import (
    ErrorEvent,
    ResponseChunk,
    SessionInit,
    ThinkingChunk,
    ToolResult,
    ToolUseStart,
    TurnComplete,
)
from cli_layout.subprocess_manager import SubprocessManager
from cli_layout.widgets import InputPanel, ScrollPanel


LAYOUTS = ["columns", "left-heavy", "right-heavy", "stacked"]


@dataclass
class Turn:
    """A single conversation turn (prompt + response)."""

    prompt: str = ""
    response: str = ""
    thinking: str = ""
    cost_usd: float | None = None
    complete: bool = False


def _build_container(layout: str) -> Container:
    """Build the multi-panel container widget tree for a given layout."""
    history = ScrollPanel("Current Prompt", id="history-panel")
    response = ScrollPanel("AI Response", id="response-panel")
    input_panel = InputPanel("Prompt (Enter to send)", id="input-section")

    if layout == "columns":
        container = Container(
            history, response, input_panel,
            id="main-container", classes="layout-columns",
        )

    elif layout == "left-heavy":
        left_stack = Vertical(history, input_panel, id="left-stack")
        container = Container(
            left_stack, response,
            id="main-container", classes="layout-left-heavy",
        )

    elif layout == "right-heavy":
        right_stack = Vertical(response, input_panel, id="right-stack")
        container = Container(
            history, right_stack,
            id="main-container", classes="layout-right-heavy",
        )

    elif layout == "stacked":
        container = Container(
            history, response, input_panel,
            id="main-container", classes="layout-stacked",
        )

    else:
        container = Container(
            history, response, input_panel,
            id="main-container", classes="layout-columns",
        )

    return container


def _build_raw_container() -> Container:
    """Build a single-panel container showing raw Claude Code output."""
    conversation = ScrollPanel("Claude Code — Raw Output", id="raw-panel")
    return Container(
        conversation,
        id="main-container", classes="layout-raw",
    )


class CLILayoutApp(App):
    """A multi-section terminal UI for AI CLI tools."""

    TITLE = "CLI Layout"
    SUB_TITLE = "Multi-section AI Terminal"
    COMMANDS = set()  # Disable command palette (frees Ctrl+P)

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        width: 100%;
        height: 100%;
    }

    /* --- Layout: columns (3 equal vertical columns) --- */
    .layout-columns {
        layout: horizontal;
    }
    .layout-columns #history-panel {
        width: 1fr;
    }
    .layout-columns #response-panel {
        width: 1fr;
    }
    .layout-columns #input-section {
        width: 1fr;
        height: 100%;
    }

    /* --- Layout: left-heavy (2 left, 1 right) --- */
    .layout-left-heavy {
        layout: horizontal;
    }
    .layout-left-heavy #left-stack {
        width: 2fr;
    }
    .layout-left-heavy #left-stack #history-panel {
        height: 1fr;
    }
    .layout-left-heavy #left-stack #input-section {
        height: auto;
        min-height: 5;
        max-height: 15;
    }
    .layout-left-heavy #response-panel {
        width: 1fr;
    }

    /* --- Layout: right-heavy (1 left, 2 right) --- */
    .layout-right-heavy {
        layout: horizontal;
    }
    .layout-right-heavy #history-panel {
        width: 1fr;
    }
    .layout-right-heavy #right-stack {
        width: 2fr;
    }
    .layout-right-heavy #right-stack #response-panel {
        height: 1fr;
    }
    .layout-right-heavy #right-stack #input-section {
        height: auto;
        min-height: 5;
        max-height: 15;
    }

    /* --- Layout: stacked (all vertical) --- */
    .layout-stacked {
        layout: vertical;
    }
    .layout-stacked #history-panel {
        height: 1fr;
    }
    .layout-stacked #response-panel {
        height: 2fr;
    }
    .layout-stacked #input-section {
        height: auto;
        min-height: 5;
        max-height: 15;
    }

    /* --- Layout: raw (single panel, full conversation) --- */
    .layout-raw {
        layout: vertical;
    }
    .layout-raw #raw-panel {
        height: 1fr;
    }

    /* Status bar */
    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+t", "toggle_raw", "Toggle View", show=True),
        Binding("ctrl+l", "cycle_layout", "Switch Layout", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("enter", "submit", "Send (in input)", show=False),
        Binding("ctrl+k", "clear_panels", "Clear", show=True),
        Binding("ctrl+p", "prev_turn", "Prev Turn", show=True, priority=True),
        Binding("ctrl+n", "next_turn", "Next Turn", show=True),
        Binding("ctrl+y", "copy_response", "Copy Response", show=True),
    ]

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self._config = config
        self._layout_index = 0
        self._subprocess: SubprocessManager | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        # Turn-based history
        self._turns: list[Turn] = []
        self._view_index: int = -1  # -1 means "live" (current in-progress turn)
        # Raw mode: single panel showing actual raw subprocess output
        self._raw_mode: bool = False
        self._raw_stdout: str = ""  # Actual raw stdout lines from backend

    @property
    def current_layout(self) -> str:
        return LAYOUTS[self._layout_index]

    @property
    def _active_turn(self) -> Turn:
        """Get or create the in-progress turn."""
        if not self._turns or self._turns[-1].complete:
            self._turns.append(Turn())
        return self._turns[-1]

    @property
    def _viewed_turn(self) -> Turn | None:
        """Get the turn currently being viewed."""
        if not self._turns:
            return None
        if self._view_index == -1:
            return self._turns[-1] if self._turns else None
        if 0 <= self._view_index < len(self._turns):
            return self._turns[self._view_index]
        return None

    def compose(self) -> ComposeResult:
        yield Header()
        yield _build_container(self.current_layout)
        yield Static(
            "Ready | Enter: Send | Ctrl+L: Layout | Ctrl+P/N: History | Ctrl+Q: Quit",
            id="status-bar",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Start the backend subprocess when the app mounts."""
        if self._config is None:
            try:
                self._config = load_config()
            except FileNotFoundError as e:
                self._update_status(f"Config error: {e}")
                return

        backend_cfg = self._config.active_backend()
        self._update_status(f"Starting {backend_cfg.name}...")

        self._subprocess = SubprocessManager(backend_cfg)
        try:
            await self._subprocess.start()
            self._reader_task = asyncio.create_task(self._read_events())
            self._stderr_task = asyncio.create_task(self._read_stderr())
            self._update_status(
                f"Connected to {backend_cfg.name} | "
                f"Enter: Send | Ctrl+P/N: History | Ctrl+L: Layout"
            )
        except FileNotFoundError as e:
            self._update_status(str(e))
        except Exception as e:
            self._update_status(f"Failed to start backend: {e}")

    def _on_raw_line(self, line: str) -> None:
        """Callback for each raw stdout line from the backend."""
        self._raw_stdout += line
        if self._raw_mode:
            self._refresh_raw()

    async def _read_events(self) -> None:
        """Background task: read events from the subprocess and route them."""
        if self._subprocess is None:
            return
        try:
            async for event in self._subprocess.read_events(
                raw_callback=self._on_raw_line,
            ):
                self._handle_event(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._update_status(f"Read error: {e}")

    async def _read_stderr(self) -> None:
        """Background task: read stderr and show errors."""
        if self._subprocess is None:
            return
        try:
            async for line in self._subprocess.read_stderr():
                if line.strip():
                    self._raw_stdout += f"[stderr] {line}\n"
                    turn = self._active_turn
                    turn.response += f"\n[stderr] {line}"
                    if self._raw_mode:
                        self._refresh_raw()
                    elif self._view_index == -1:
                        self._refresh_response()
        except asyncio.CancelledError:
            pass

    def _handle_event(self, event) -> None:
        """Route a normalized event to the active turn."""
        turn = self._active_turn

        if isinstance(event, SessionInit):
            self._update_status(
                f"Session: {event.session_id[:8]}... | "
                f"Model: {event.model} | "
                f"Enter: Send | Ctrl+P/N: History"
            )

        elif isinstance(event, ThinkingChunk):
            turn.thinking += event.text
            if self._view_index == -1 and not self._raw_mode:
                self._refresh_response()

        elif isinstance(event, ResponseChunk):
            turn.response += event.text
            if self._view_index == -1 and not self._raw_mode:
                self._refresh_response()

        elif isinstance(event, ToolUseStart):
            turn.response += f"\n\n---\n**Tool: {event.tool_name}**\n"
            if self._view_index == -1 and not self._raw_mode:
                self._refresh_response()

        elif isinstance(event, ToolResult):
            output = event.output
            if len(output) > 500:
                output = output[:500] + "... (truncated)"
            turn.response += f"\n```\n{output}\n```\n"
            if self._view_index == -1 and not self._raw_mode:
                self._refresh_response()

        elif isinstance(event, TurnComplete):
            turn.cost_usd = event.cost_usd
            turn.complete = True

            cost_str = f"${event.cost_usd:.4f}" if event.cost_usd else "N/A"
            turn_num = len(self._turns)
            self._update_status(
                f"Turn {turn_num}/{len(self._turns)} | Cost: {cost_str} | "
                f"Enter: Send | Ctrl+P/N: History"
            )

            if self._view_index == -1 and not self._raw_mode:
                self._refresh_view()

        elif isinstance(event, ErrorEvent):
            turn.response += f"\n[ERROR] {event.message}\n"
            if self._view_index == -1 and not self._raw_mode:
                self._refresh_response()

    def _refresh_raw(self) -> None:
        """Refresh the raw output panel with actual subprocess stdout."""
        try:
            raw_panel = self.query_one("#raw-panel", ScrollPanel)
            raw_panel.set_text(self._raw_stdout)
            raw_panel.scroll_end(animate=False)
        except Exception:
            pass

    def _refresh_view(self) -> None:
        """Refresh both panels to show the viewed turn."""
        turn = self._viewed_turn
        try:
            prompt_panel = self.query_one("#history-panel", ScrollPanel)
            response_panel = self.query_one("#response-panel", ScrollPanel)
        except Exception:
            return

        if turn is None:
            prompt_panel.set_text("")
            response_panel.set_text("")
            return

        # Update prompt panel title with turn indicator
        self._update_prompt_title()

        prompt_panel.set_text(turn.prompt if turn.prompt else "(no prompt yet)")
        response_panel.set_markdown(turn.response)
        response_panel.scroll_end(animate=False)

    def _refresh_response(self) -> None:
        """Refresh only the response panel (for streaming)."""
        turn = self._viewed_turn
        if turn is None:
            return
        try:
            response_panel = self.query_one("#response-panel", ScrollPanel)
            response_panel.set_markdown(turn.response)
            response_panel.scroll_end(animate=False)
        except Exception:
            pass

    def _update_prompt_title(self) -> None:
        """Update the prompt panel title to show turn position."""
        try:
            title_widget = self.query_one(
                "#history-panel .panel-title", Static
            )
        except Exception:
            return

        total = len(self._turns)
        if total == 0:
            title_widget.update("Current Prompt")
            return

        if self._view_index == -1:
            idx = total
        else:
            idx = self._view_index + 1

        title_widget.update(f"Prompt [{idx}/{total}]")

    # Claude CLI commands that can be run as standalone subcommands
    _CLAUDE_COMMANDS: dict[str, list[str]] = {
        "/usage": ["usage"],
        "/config": ["config", "list"],
        "/model": ["model", "get"],
        "/status": ["status"],
        "/version": ["--version"],
    }

    async def _run_claude_command(self, prompt: str) -> None:
        """Run a Claude CLI command as a subprocess and show the output."""
        cmd_key = prompt.split()[0].lower()
        args_suffix = self._CLAUDE_COMMANDS.get(cmd_key)
        if args_suffix is None:
            return

        backend_cmd = "claude"
        if self._config:
            backend_cmd = self._config.active_backend().command

        self._view_index = -1
        turn = self._active_turn
        turn.prompt = prompt
        self._refresh_view()
        self._update_status(f"Running {cmd_key}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                backend_cmd, *args_suffix,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode("utf-8", errors="replace").strip()
            turn.response = output if output else "(no output)"
        except asyncio.TimeoutError:
            turn.response = f"[ERROR] {cmd_key} timed out"
        except FileNotFoundError:
            turn.response = f"[ERROR] '{backend_cmd}' not found in PATH"
        except Exception as e:
            turn.response = f"[ERROR] {e}"

        turn.complete = True
        self._refresh_view()
        self._update_status(f"{cmd_key} complete | Enter: Send | Ctrl+P/N: History")

    async def on_input_panel_submitted(self, message: InputPanel.Submitted) -> None:
        """Handle prompt submission from the input panel."""
        prompt = message.value
        if not prompt:
            return

        # Handle /layout command locally
        if prompt.startswith("/layout"):
            parts = prompt.split()
            if len(parts) > 1 and parts[1] in LAYOUTS:
                self._layout_index = LAYOUTS.index(parts[1])
                await self._rebuild_layout()
            else:
                await self.action_cycle_layout()
            return

        # Handle Claude CLI commands
        cmd_key = prompt.split()[0].lower()
        if cmd_key in self._CLAUDE_COMMANDS:
            await self._run_claude_command(prompt)
            return

        # Jump back to live view
        self._view_index = -1

        # Create a new turn with this prompt
        turn = self._active_turn
        turn.prompt = prompt

        # Show the prompt in the left panel
        self._refresh_view()

        # Send to backend
        if self._subprocess and self._subprocess.is_running:
            self._update_status("Waiting for response...")
            try:
                await self._subprocess.send_prompt(prompt)
            except Exception as e:
                turn.response += f"\n[ERROR] Failed to send: {e}\n"
                self._refresh_response()
        else:
            turn.response += "\n[ERROR] Backend not running. Restart the app.\n"
            self._refresh_response()

    def action_prev_turn(self) -> None:
        """Navigate to the previous turn."""
        if not self._turns:
            return

        if self._view_index == -1:
            # From live view, find the last completed turn
            # (skip the current in-progress turn if it exists)
            target = len(self._turns) - 1
            if not self._turns[target].complete and target > 0:
                target -= 1
            self._view_index = target
        elif self._view_index > 0:
            self._view_index -= 1
        else:
            return  # Already at first turn

        self._refresh_view()
        self._update_nav_status()

    def action_next_turn(self) -> None:
        """Navigate to the next turn."""
        if not self._turns:
            return

        if self._view_index == -1:
            return  # Already at live

        if self._view_index < len(self._turns) - 1:
            self._view_index += 1
        else:
            # Go back to live view
            self._view_index = -1

        self._refresh_view()
        self._update_nav_status()

    def _update_nav_status(self) -> None:
        """Update status bar with navigation info."""
        total = len(self._turns)
        if self._view_index == -1:
            label = f"Turn {total}/{total} (live)"
        else:
            label = f"Turn {self._view_index + 1}/{total}"
        self._update_status(
            f"{label} | Ctrl+P: Prev | Ctrl+N: Next | Enter: Send"
        )

    async def action_toggle_raw(self) -> None:
        """Toggle between multi-panel layout and raw conversation view."""
        self._raw_mode = not self._raw_mode
        await self._rebuild_layout()

    async def _rebuild_layout(self) -> None:
        """Rebuild the layout, preserving turn data."""
        # Remove old container
        try:
            old = self.query_one("#main-container")
            await old.remove()
        except Exception:
            pass

        # Build the appropriate container
        if self._raw_mode:
            new_container = _build_raw_container()
        else:
            new_container = _build_container(self.current_layout)

        status = self.query_one("#status-bar")
        await self.mount(new_container, before=status)

        # Restore content
        if self._raw_mode:
            self._refresh_raw()
            self._update_status(
                "Raw View | Ctrl+T: Toggle Layout | Ctrl+Q: Quit"
            )
        else:
            self._refresh_view()
            try:
                self.query_one("#prompt-input").focus()
            except Exception:
                pass
            self._update_status(
                f"Layout: {self.current_layout} | Ctrl+T: Raw View | "
                f"Enter: Send | Ctrl+L: Layout"
            )

    async def action_cycle_layout(self) -> None:
        """Cycle through available layouts."""
        self._layout_index = (self._layout_index + 1) % len(LAYOUTS)
        await self._rebuild_layout()

    def action_copy_response(self) -> None:
        """Copy the current response text to clipboard."""
        turn = self._viewed_turn
        if turn is None:
            self._update_status("Nothing to copy")
            return

        text = turn.response if not self._raw_mode else self._raw_stdout
        if not text:
            self._update_status("Nothing to copy")
            return

        self.copy_to_clipboard(text)
        self._update_status("Copied to clipboard! (Shift+drag to select text)")

    def action_clear_panels(self) -> None:
        """Clear all panel content."""
        try:
            self.query_one("#history-panel", ScrollPanel).clear_content()
            self.query_one("#response-panel", ScrollPanel).clear_content()
        except Exception:
            pass

    def _update_status(self, text: str) -> None:
        try:
            self.query_one("#status-bar", Static).update(text)
        except Exception:
            pass

    async def action_quit(self) -> None:
        """Clean up and quit."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._stderr_task:
            self._stderr_task.cancel()
        if self._subprocess:
            await self._subprocess.stop()
        self.exit()


def main() -> None:
    """Entry point for the CLI Layout app."""
    import argparse

    parser = argparse.ArgumentParser(
        description="CLI Layout - Multi-section AI Terminal UI"
    )
    parser.add_argument(
        "-c", "--config", help="Path to config.yaml", default=None,
    )
    parser.add_argument(
        "-l", "--layout", choices=LAYOUTS, default="columns",
        help="Initial layout (default: columns)",
    )
    parser.add_argument(
        "-b", "--backend", help="Override the backend from config", default=None,
    )
    args = parser.parse_args()

    config = load_config(args.config)
    if args.backend:
        config.backend = args.backend

    app = CLILayoutApp(config=config)
    app._layout_index = LAYOUTS.index(args.layout)
    app.run()


if __name__ == "__main__":
    main()
