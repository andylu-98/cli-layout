"""Custom Textual widgets for the CLI Layout app."""

from __future__ import annotations

from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static, TextArea


class ScrollPanel(VerticalScroll):
    """A scrollable panel that displays text content."""

    DEFAULT_CSS = """
    ScrollPanel {
        border: solid $primary;
        padding: 0 1;
        overflow-y: auto;
    }
    ScrollPanel .panel-title {
        text-style: bold;
        color: $text;
        background: $primary;
        padding: 0 1;
        width: 100%;
    }
    ScrollPanel .panel-content {
        width: 100%;
    }
    """

    title_text: reactive[str] = reactive("")

    def __init__(
        self,
        title: str = "",
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.title_text = title

    def compose(self) -> ComposeResult:
        yield Static(self.title_text, classes="panel-title")
        yield Static("", classes="panel-content", id=f"{self.id}-content")

    def append_text(self, text: str) -> None:
        """Append text to the panel content and scroll to bottom."""
        content = self.query_one(f"#{self.id}-content", Static)
        current = str(content.renderable)
        content.update(current + text)
        self.scroll_end(animate=False)

    def set_text(self, text: str) -> None:
        """Replace the panel content."""
        content = self.query_one(f"#{self.id}-content", Static)
        content.update(text)

    def set_markdown(self, text: str) -> None:
        """Replace the panel content, rendered as Markdown."""
        content = self.query_one(f"#{self.id}-content", Static)
        if text.strip():
            content.update(Markdown(text))
        else:
            content.update("")

    def clear_content(self) -> None:
        """Clear the panel content."""
        self.set_text("")


class SubmitTextArea(TextArea):
    """TextArea where Enter submits and Shift+Enter inserts a newline."""

    class SubmitRequested(Message):
        """Posted when the user presses Enter to submit."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    async def _on_key(self, event) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                self.post_message(self.SubmitRequested(text))
                self.clear()
        else:
            await super()._on_key(event)


class InputPanel(Widget):
    """Full-height text input panel with submit capability."""

    DEFAULT_CSS = """
    InputPanel {
        border: solid $accent;
        padding: 0;
    }
    InputPanel .input-title {
        text-style: bold;
        color: $text;
        background: $accent;
        padding: 0 1;
        width: 100%;
        height: 1;
    }
    InputPanel SubmitTextArea {
        height: 1fr;
    }
    """

    class Submitted(Message):
        """Posted when the user submits input."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(
        self,
        title: str = "Input",
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="input-title")
        yield SubmitTextArea(id="prompt-input")

    def on_mount(self) -> None:
        ta = self.query_one("#prompt-input", SubmitTextArea)
        ta.focus()

    def on_submit_text_area_submit_requested(
        self, message: SubmitTextArea.SubmitRequested
    ) -> None:
        """Forward the submit from our custom TextArea."""
        self.post_message(self.Submitted(message.value))

    @property
    def text_area(self) -> SubmitTextArea:
        return self.query_one("#prompt-input", SubmitTextArea)
