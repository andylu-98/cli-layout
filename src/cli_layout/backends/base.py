"""Base class for backend parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Generator

from cli_layout.events import Event


class BaseParser(ABC):
    """Abstract parser that converts raw backend output into normalized events."""

    @abstractmethod
    def feed_line(self, line: str) -> Generator[Event, None, None]:
        """Feed a line of output from the backend process.

        Yields zero or more normalized Event objects.
        """
        ...
