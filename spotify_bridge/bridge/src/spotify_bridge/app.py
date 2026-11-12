"""Wires the pieces together.

Phase 1: librespot events drive the state machine, the PCM reader drains the
FIFO in real time, and both are logged. Phase 2 plugs the Sendspin source in
where marked.
"""

from __future__ import annotations

import asyncio
import logging
import math
import signal
import sys

from spotify_bridge import EVENT_SOCKET_PATH, FIFO_PATH
from spotify_bridge.config import Config
from spotify_bridge.events import EventServer
from spotify_bridge.pcm import CHUNK_MS, PcmReader, level_dbfs
from spotify_bridge.state import PlayerStateMachine, Snapshot

log = logging.getLogger("spotify_bridge")

LEVEL_LOG_INTERVAL_S = 5.0


def describe(snapshot: Snapshot) -> str:
    track = snapshot.track
    parts = [snapshot.state.value]
    if track.title:
        artists = ", ".join(track.artists)
        parts.append(f"'{track.title}'" + (f" by {artists}" if artists else ""))
    if snapshot.volume_percent is not None:
        parts.append(f"volume {snapshot.volume_percent}%")
    if snapshot.client_name:
        parts.append(f"from {snapshot.client_name}")
    return ", ".join(parts)


class Bridge:
    def __init__(
        self,
        config: Config,
        fifo_path: str = FIFO_PATH,
        event_socket_path: str = EVENT_SOCKET_PATH,
    ) -> None:
        self.config = config
        self.state = PlayerStateMachine()
        self.state.add_listener(self._on_state_change)
        self.events = EventServer(event_socket_path, self.state.apply)
        self.pcm = PcmReader(fifo_path, self._on_chunk)
        self._chunks_since_log = 0
        self._peak_dbfs = -math.inf
        self._stopped = asyncio.Event()

    def _on_state_change(self, old: Snapshot, new: Snapshot) -> None:
        if old.state is not new.state or old.track != new.track:
            log.info("Player: %s", describe(new))
        elif old.volume_percent != new.volume_percent:
            log.info("Spotify volume: %s%%", new.volume_percent)
        if old.signal_present != new.signal_present:
            # Phase 2: report SignalState.PRESENT / ABSENT to Music Assistant here.
            log.info("Signal %s", "present" if new.signal_present else "absent")

    def _on_chunk(self, chunk: bytes, tick_time: float) -> None:
        # Phase 2: feed the chunk to the Sendspin SourceCapture while MA asks for audio.
        self._chunks_since_log += 1
        if self._chunks_since_log % 10 == 0:  # sample the level every 200 ms
            self._peak_dbfs = max(self._peak_dbfs, level_dbfs(chunk))
        if self._chunks_since_log * CHUNK_MS / 1000 >= LEVEL_LOG_INTERVAL_S:
            log.info(
                "Audio flowing: %d chunks in %.0f s, loudest %.1f dBFS",
                self._chunks_since_log,
                LEVEL_LOG_INTERVAL_S,
                self._peak_dbfs,
            )
            self._chunks_since_log = 0
            self._peak_dbfs = -math.inf

    async def run(self) -> None:
        await self.events.start()
        self.pcm.start()
        log.info("Spotify Bridge running for Spotify device '%s'", self.config.name)
        await self._stopped.wait()

    async def close(self) -> None:
        await self.pcm.stop()
        self.events.close()

    def request_stop(self) -> None:
        self._stopped.set()


async def run(config: Config) -> None:
    bridge = Bridge(config)
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, bridge.request_stop)
    try:
        await bridge.run()
    finally:
        await bridge.close()
        log.info("Spotify Bridge stopped")
