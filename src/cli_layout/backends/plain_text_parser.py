"""Fallback parser for backends that output plain text."""

from __future__ import annotations

from collections.abc import Generator

from cli_layout.events import Event, ResponseChunk

from .base import BaseParser


class PlainTextParser(BaseParser):
    """Treats every line of output as a response chunk.

    Use this as a starting point for backends that don't have structured output.
    """

    def feed_line(self, line: str) -> Generator[Event, None, None]:
        if line.strip():
            yield ResponseChunk(text=line)
