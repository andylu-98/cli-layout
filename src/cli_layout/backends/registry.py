"""Registry mapping parser names (from config) to parser classes."""

from __future__ import annotations

from .base import BaseParser
from .claude_parser import ClaudeParser
from .plain_text_parser import PlainTextParser

PARSERS: dict[str, type[BaseParser]] = {
    "claude": ClaudeParser,
    "plain_text": PlainTextParser,
}


def get_parser(name: str) -> BaseParser:
    cls = PARSERS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown parser '{name}'. Available: {list(PARSERS.keys())}"
        )
    return cls()
