"""Normalized events emitted by backend parsers.

The TUI only consumes these events — it never sees raw backend output.
Adding a new backend means writing a parser that emits these events.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThinkingChunk:
    """A chunk of the model's thinking/reasoning process."""

    text: str


@dataclass
class ResponseChunk:
    """A chunk of the model's visible response text."""

    text: str


@dataclass
class ToolUseStart:
    """The model started using a tool."""

    tool_name: str
    tool_id: str = ""


@dataclass
class ToolResult:
    """Result returned from a tool invocation."""

    tool_name: str
    output: str
    tool_id: str = ""


@dataclass
class SessionInit:
    """Backend session initialized with metadata."""

    session_id: str
    model: str = ""
    extras: dict = field(default_factory=dict)


@dataclass
class TurnComplete:
    """A full assistant turn has completed."""

    cost_usd: float = 0.0
    duration_ms: int = 0


@dataclass
class ErrorEvent:
    """An error occurred in the backend."""

    message: str


# Union type for all events
Event = (
    ThinkingChunk
    | ResponseChunk
    | ToolUseStart
    | ToolResult
    | SessionInit
    | TurnComplete
    | ErrorEvent
)
