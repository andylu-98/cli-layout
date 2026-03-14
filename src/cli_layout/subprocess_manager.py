"""Manages the AI CLI backend as an async subprocess."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncGenerator

from cli_layout.backends.base import BaseParser
from cli_layout.backends.registry import get_parser
from cli_layout.config import BackendConfig
from cli_layout.events import ErrorEvent, Event


class SubprocessManager:
    """Spawns and communicates with the AI CLI backend process."""

    def __init__(self, config: BackendConfig) -> None:
        self.config = config
        self.parser: BaseParser = get_parser(config.parser)
        self._process: asyncio.subprocess.Process | None = None
        self._session_id: str | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def start(self, resume: bool = False) -> None:
        """Start the backend subprocess."""
        cmd = shutil.which(self.config.command)
        if cmd is None:
            raise FileNotFoundError(
                f"Command '{self.config.command}' not found in PATH. "
                f"Is it installed?"
            )

        args = list(self.config.args)
        if resume and self.config.resume_args:
            args.extend(self.config.resume_args)

        self._process = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def send_prompt(self, prompt: str) -> None:
        """Send a prompt to the backend process via stdin."""
        if not self.is_running or self._process.stdin is None:
            raise RuntimeError("Backend process is not running")

        if self.config.input_format == "stream-json":
            message = json.dumps({
                "type": "user",
                "message": {"role": "user", "content": prompt},
            })
            self._process.stdin.write((message + "\n").encode())
        else:
            self._process.stdin.write((prompt + "\n").encode())

        await self._process.stdin.drain()

    async def read_events(
        self,
        raw_callback: callable = None,
    ) -> AsyncGenerator[Event, None]:
        """Read and parse events from the backend stdout stream.

        If raw_callback is provided, each raw stdout line is passed to it
        before parsing.
        """
        if not self.is_running or self._process.stdout is None:
            return

        while True:
            try:
                line = await self._process.stdout.readline()
            except asyncio.CancelledError:
                return

            if not line:
                break

            decoded = line.decode("utf-8", errors="replace")

            if raw_callback is not None:
                raw_callback(decoded)

            for event in self.parser.feed_line(decoded):
                yield event

    async def read_stderr(self) -> AsyncGenerator[str, None]:
        """Read stderr lines from the backend process."""
        if not self.is_running or self._process.stderr is None:
            return

        while True:
            try:
                line = await self._process.stderr.readline()
            except asyncio.CancelledError:
                return

            if not line:
                break

            yield line.decode("utf-8", errors="replace").rstrip()

    async def stop(self) -> None:
        """Terminate the backend process."""
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
