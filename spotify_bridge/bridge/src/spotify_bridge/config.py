"""Add-on options (``/data/options.json``) as a typed object."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

OPTIONS_PATH = "/data/options.json"
DEFAULT_STATE_DIR = "/data/sendspin"
# The Music Assistant app runs on the host network, like this app.
DEFAULT_MA_URL = "ws://localhost:8927/sendspin"

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

log = logging.getLogger(__name__)


def _opt_str(options: dict[str, object], key: str) -> str:
    value = options.get(key)
    return str(value).strip() if value is not None else ""


@dataclass(frozen=True)
class Config:
    name: str = "Home Assistant"
    log_level: int = logging.INFO
    music_assistant_url: str = DEFAULT_MA_URL
    sendspin_name: str = ""
    pairing_code: str | None = None
    state_dir: str = DEFAULT_STATE_DIR

    @property
    def source_name(self) -> str:
        """Name of the Live Input in Music Assistant."""
        return self.sendspin_name or f"Spotify ({self.name})"

    @classmethod
    def from_dict(cls, options: dict[str, object]) -> Config:
        name = _opt_str(options, "name") or cls.name
        level_name = (_opt_str(options, "log_level") or "info").lower()
        url = _opt_str(options, "music_assistant_url") or DEFAULT_MA_URL
        code = re.sub(r"[\s-]", "", _opt_str(options, "pairing_code"))
        if code and not re.fullmatch(r"\d{8}", code):
            log.warning("pairing_code must be 8 digits; ignoring it and using on-screen codes")
            code = ""
        return cls(
            name=name,
            log_level=_LOG_LEVELS.get(level_name, logging.INFO),
            music_assistant_url=url,
            sendspin_name=_opt_str(options, "sendspin_name"),
            pairing_code=code or None,
            state_dir=os.environ.get("SPOTIFY_BRIDGE_STATE_DIR", DEFAULT_STATE_DIR),
        )


def load_config(path: str | None = None) -> Config:
    """Load options; a missing or unreadable file gives the defaults."""
    path = path or os.environ.get("SPOTIFY_BRIDGE_OPTIONS", OPTIONS_PATH)
    try:
        options = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Config.from_dict({})
    return Config.from_dict(options if isinstance(options, dict) else {})
