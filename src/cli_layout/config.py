"""Configuration loader for CLI Layout."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class BackendConfig:
    """Configuration for a single AI CLI backend."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    output_format: str = "text"
    input_format: str = "stdin"
    resume_args: list[str] = field(default_factory=list)
    parser: str = "plain_text"


@dataclass
class AppConfig:
    """Top-level application configuration."""

    backend: str
    backends: dict[str, BackendConfig]

    def active_backend(self) -> BackendConfig:
        if self.backend not in self.backends:
            raise ValueError(
                f"Backend '{self.backend}' not found. "
                f"Available: {list(self.backends.keys())}"
            )
        return self.backends[self.backend]


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load configuration from a YAML file.

    Search order:
    1. Explicit path argument
    2. CLI_LAYOUT_CONFIG environment variable
    3. ./config.yaml (current directory)
    4. ~/.config/cli-layout/config.yaml
    """
    if path is None:
        env_path = os.environ.get("CLI_LAYOUT_CONFIG")
        if env_path:
            path = Path(env_path)
        elif Path("config.yaml").exists():
            path = Path("config.yaml")
        elif Path.home().joinpath(".config", "cli-layout", "config.yaml").exists():
            path = Path.home() / ".config" / "cli-layout" / "config.yaml"
        else:
            raise FileNotFoundError(
                "No config.yaml found. Create one in the current directory "
                "or at ~/.config/cli-layout/config.yaml"
            )

    path = Path(path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    backends: dict[str, BackendConfig] = {}
    for name, cfg in raw.get("backends", {}).items():
        backends[name] = BackendConfig(
            name=name,
            command=cfg.get("command", name),
            args=cfg.get("args", []),
            output_format=cfg.get("output_format", "text"),
            input_format=cfg.get("input_format", "stdin"),
            resume_args=cfg.get("resume_args", []),
            parser=cfg.get("parser", "plain_text"),
        )

    return AppConfig(
        backend=raw.get("backend", "claude"),
        backends=backends,
    )
