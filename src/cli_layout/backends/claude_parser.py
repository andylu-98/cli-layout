"""Parser for Claude Code's stream-json output format."""

from __future__ import annotations

import json
from collections.abc import Generator

from cli_layout.events import (
    ErrorEvent,
    Event,
    ResponseChunk,
    SessionInit,
    ThinkingChunk,
    ToolResult,
    ToolUseStart,
    TurnComplete,
)

from .base import BaseParser


class ClaudeParser(BaseParser):
    """Parses Claude Code --output-format stream-json lines into events."""

    def feed_line(self, line: str) -> Generator[Event, None, None]:
        line = line.strip()
        if not line:
            return

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            yield ErrorEvent(message=f"Invalid JSON: {line[:100]}")
            return

        msg_type = data.get("type", "")

        if msg_type == "system" and data.get("subtype") == "init":
            yield SessionInit(
                session_id=data.get("session_id", ""),
                model=data.get("model", ""),
                extras={
                    k: data[k]
                    for k in ("tools", "claude_code_version")
                    if k in data
                },
            )

        elif msg_type == "assistant":
            message = data.get("message", {})
            content_blocks = message.get("content", [])
            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "thinking":
                    text = block.get("thinking", "")
                    if text:
                        yield ThinkingChunk(text=text)
                elif block_type == "text":
                    text = block.get("text", "")
                    if text:
                        yield ResponseChunk(text=text)
                elif block_type == "tool_use":
                    yield ToolUseStart(
                        tool_name=block.get("name", "unknown"),
                        tool_id=block.get("id", ""),
                    )
                elif block_type == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, list):
                        content = "\n".join(
                            c.get("text", str(c)) for c in content
                        )
                    yield ToolResult(
                        tool_name=block.get("name", "tool"),
                        output=str(content),
                        tool_id=block.get("tool_use_id", ""),
                    )

            if data.get("error"):
                yield ErrorEvent(message=data["error"])

        elif msg_type == "result":
            yield TurnComplete(
                cost_usd=data.get("total_cost_usd", 0.0),
                duration_ms=data.get("duration_ms", 0),
            )
            if data.get("is_error"):
                result_text = data.get("result", "")
                if result_text:
                    yield ErrorEvent(message=result_text)
