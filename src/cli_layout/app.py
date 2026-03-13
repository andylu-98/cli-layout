"""Main Textual application for CLI Layout."""

from __future__ import annotations

import asyncio
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


def _build_container(layout: str) -> Container:
    """Build the main container widget tree for a given layout.

    This constructs widgets imperatively (no compose context needed),
    so it can be called at any time — during compose or after mount.
    """
    history = ScrollPanel("Conversation History", id="history-panel")
    response = ScrollPanel("AI Response", id="response-panel")
    input_panel = InputPanel("Prompt (Ctrl+S to send)", id="input-section")

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


class CLILayoutApp(App):
    """A multi-section terminal UI for AI CLI tools."""

    TITLE = "CLI Layout"
    SUB_TITLE = "Multi-section AI Terminal"

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
        Binding("ctrl+l", "cycle_layout", "Switch Layout", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+s", "submit", "Send (in input)", show=True),
        Binding("ctrl+k", "clear_panels", "Clear", show=True),
    ]

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self._config = config
        self._layout_index = 0
        self._subprocess: SubprocessManager | None = None
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._turn_count = 0
        self._current_thinking = ""
        self._current_response = ""

    @property
    def current_layout(self) -> str:
        return LAYOUTS[self._layout_index]

    def compose(self) -> ComposeResult:
        yield Header()
        yield _build_container(self.current_layout)
        yield Static(
            "Ready | Ctrl+S: Send | Ctrl+L: Layout | Ctrl+Q: Quit",
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
                f"Ctrl+S: Send | Ctrl+L: Layout | Ctrl+Q: Quit"
            )
        except FileNotFoundError as e:
            self._update_status(str(e))
        except Exception as e:
            self._update_status(f"Failed to start backend: {e}")

    async def _read_events(self) -> None:
        """Background task: read events from the subprocess and route them."""
        if self._subprocess is None:
            return
        try:
            async for event in self._subprocess.read_events():
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
                    try:
                        panel = self.query_one("#response-panel", ScrollPanel)
                        panel.append_text(f"\n[stderr] {line}")
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    def _handle_event(self, event) -> None:
        """Route a normalized event to the appropriate panel."""
        try:
            response_panel = self.query_one("#response-panel", ScrollPanel)
        except Exception:
            return

        if isinstance(event, SessionInit):
            self._update_status(
                f"Session: {event.session_id[:8]}... | "
                f"Model: {event.model} | "
                f"Ctrl+S: Send | Ctrl+L: Layout"
            )

        elif isinstance(event, ThinkingChunk):
            self._current_thinking += event.text
            response_panel.append_text(event.text)

        elif isinstance(event, ResponseChunk):
            self._current_response += event.text
            response_panel.append_text(event.text)

        elif isinstance(event, ToolUseStart):
            response_panel.append_text(f"\n--- Tool: {event.tool_name} ---\n")

        elif isinstance(event, ToolResult):
            output = event.output
            if len(output) > 500:
                output = output[:500] + "... (truncated)"
            response_panel.append_text(f"\n[{event.tool_name} result]: {output}\n")

        elif isinstance(event, TurnComplete):
            self._turn_count += 1
            response_panel.append_text(f"\n{'=' * 40}\n")

            try:
                history = self.query_one("#history-panel", ScrollPanel)
                if self._current_response:
                    summary = self._current_response[:200]
                    if len(self._current_response) > 200:
                        summary += "..."
                    history.append_text(
                        f"\n--- Turn {self._turn_count} ---\n"
                        f"Response preview: {summary}\n"
                    )
            except Exception:
                pass

            self._current_thinking = ""
            self._current_response = ""

            cost_str = f"${event.cost_usd:.4f}" if event.cost_usd else "N/A"
            self._update_status(
                f"Turn {self._turn_count} complete | Cost: {cost_str} | Ctrl+S: Send"
            )

        elif isinstance(event, ErrorEvent):
            response_panel.append_text(f"\n[ERROR] {event.message}\n")

    async def on_input_panel_submitted(self, message: InputPanel.Submitted) -> None:
        """Handle prompt submission from the input panel."""
        prompt = message.value
        if not prompt:
            return

        # Log prompt to history
        try:
            history = self.query_one("#history-panel", ScrollPanel)
            history.append_text(f"\n> {prompt}\n")
        except Exception:
            pass

        # Handle /layout command locally
        if prompt.startswith("/layout"):
            parts = prompt.split()
            if len(parts) > 1 and parts[1] in LAYOUTS:
                self._layout_index = LAYOUTS.index(parts[1])
                await self._rebuild_layout()
            else:
                await self.action_cycle_layout()
            return

        # Send to backend
        try:
            response = self.query_one("#response-panel", ScrollPanel)
            response.append_text(f"\n{'─' * 30}\n")
        except Exception:
            pass

        if self._subprocess and self._subprocess.is_running:
            self._update_status("Waiting for response...")
            try:
                await self._subprocess.send_prompt(prompt)
            except Exception as e:
                try:
                    response = self.query_one("#response-panel", ScrollPanel)
                    response.append_text(f"\n[ERROR] Failed to send: {e}\n")
                except Exception:
                    pass
        else:
            try:
                response = self.query_one("#response-panel", ScrollPanel)
                response.append_text(
                    "\n[ERROR] Backend not running. Restart the app.\n"
                )
            except Exception:
                pass

    async def _rebuild_layout(self) -> None:
        """Rebuild the layout, preserving panel content."""
        # Save current content
        history_content = ""
        response_content = ""
        try:
            history_content = str(
                self.query_one("#history-panel-content", Static).renderable
            )
            response_content = str(
                self.query_one("#response-panel-content", Static).renderable
            )
        except Exception:
            pass

        # Remove old container
        try:
            old = self.query_one("#main-container")
            await old.remove()
        except Exception:
            pass

        # Build and mount new container
        new_container = _build_container(self.current_layout)
        status = self.query_one("#status-bar")
        await self.mount(new_container, before=status)

        # Restore content
        try:
            self.query_one("#history-panel", ScrollPanel).set_text(history_content)
            self.query_one("#response-panel", ScrollPanel).set_text(response_content)
            self.query_one("#prompt-input").focus()
        except Exception:
            pass

        self._update_status(
            f"Layout: {self.current_layout} | Ctrl+S: Send | Ctrl+L: Layout"
        )

    async def action_cycle_layout(self) -> None:
        """Cycle through available layouts."""
        self._layout_index = (self._layout_index + 1) % len(LAYOUTS)
        await self._rebuild_layout()

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
