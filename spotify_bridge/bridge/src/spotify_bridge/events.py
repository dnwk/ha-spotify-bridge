"""Receives librespot events from the ``spotify-bridge-event`` hook (Unix datagrams)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from collections.abc import Callable

log = logging.getLogger(__name__)


def parse_datagram(data: bytes) -> dict[str, str] | None:
    """Decode one hook datagram. Returns None for anything malformed."""
    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, dict) or not isinstance(decoded.get("PLAYER_EVENT"), str):
        return None
    return {str(k): str(v) for k, v in decoded.items() if v is not None}


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, on_event: Callable[[dict[str, str]], None]) -> None:
        self._on_event = on_event

    def datagram_received(self, data: bytes, addr: object) -> None:
        event = parse_datagram(data)
        if event is None:
            log.warning("Ignoring malformed event datagram (%d bytes)", len(data))
            return
        self._on_event(event)


class EventServer:
    """Listens on a Unix datagram socket for hook events."""

    def __init__(self, path: str, on_event: Callable[[dict[str, str]], None]) -> None:
        self._path = path
        self._on_event = on_event
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(self._path)
        # librespot runs the hook as the same user (root in the container).
        os.chmod(self._path, 0o600)
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _Protocol(self._on_event), sock=sock
        )
        log.info("Listening for librespot events on %s", self._path)

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        try:
            os.unlink(self._path)
        except FileNotFoundError:
            pass
