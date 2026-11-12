"""Add-on options (``/data/options.json``) as a typed object."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

OPTIONS_PATH = "/data/options.json"

# bashio log levels (add-on option) -> Python logging levels.
_LOG_LEVELS = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


@dataclass(frozen=True)
class Config:
    name: str = "Home Assistant"
    log_level: int = logging.INFO

    @classmethod
    def from_dict(cls, options: dict[str, object]) -> Config:
        name = str(options.get("name") or cls.name)
        level_name = str(options.get("log_level") or "info").lower()
        return cls(name=name, log_level=_LOG_LEVELS.get(level_name, logging.INFO))


def load_config(path: str | None = None) -> Config:
    """Load options; a missing or unreadable file gives the defaults."""
    path = path or os.environ.get("SPOTIFY_BRIDGE_OPTIONS", OPTIONS_PATH)
    try:
        options = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config()
    return Config.from_dict(options if isinstance(options, dict) else {})
