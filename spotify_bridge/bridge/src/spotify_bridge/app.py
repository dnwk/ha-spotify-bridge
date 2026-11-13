"""Wires the pieces together.

librespot events drive the state machine; its ``signal_present`` becomes the
Sendspin line-sense signal. The PCM reader drains the FIFO in real time and
hands each chunk to the Sendspin source, which forwards it while Music
Assistant is asking for audio.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import signal
import sys
from pathlib import Path

from spotify_bridge import EVENT_SOCKET_PATH, FIFO_PATH
from spotify_bridge.config import Config
from spotify_bridge.events import EventServer
from spotify_bridge.ha import HomeAssistant
from spotify_bridge.pcm import CHUNK_MS, PcmReader, level_dbfs
from spotify_bridge.sendspin_source import SendspinSource
from spotify_bridge.state import PlayerStateMachine, Snapshot

log = logging.getLogger("spotify_bridge")

LEVEL_LOG_INTERVAL_S = 30.0


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
        source: SendspinSource | None = None,
    ) -> None:
        self.config = config
        self.source = source
        self.failed = False
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
            log.info("Signal %s", "present" if new.signal_present else "absent")
            if self.source is not None:
                self.source.set_signal(new.signal_present)

    async def _on_chunk(self, chunk: bytes, tick_time: float) -> None:
        if self.source is not None:
            await self.source.feed(chunk, tick_time)
        self._chunks_since_log += 1
        if self._chunks_since_log % 10 == 0:  # sample the level every 200 ms
            self._peak_dbfs = max(self._peak_dbfs, level_dbfs(chunk))
        if self._chunks_since_log * CHUNK_MS / 1000 >= LEVEL_LOG_INTERVAL_S:
            log.info(
                "Audio flowing: %d chunks in %.0f s, loudest %.1f dBFS, %s",
                self._chunks_since_log,
                LEVEL_LOG_INTERVAL_S,
                self._peak_dbfs,
                "streaming to Music Assistant"
                if self.source is not None and self.source.streaming
                else "not streaming (Music Assistant has not asked for audio)",
            )
            self._chunks_since_log = 0
            self._peak_dbfs = -math.inf

    async def run(self) -> None:
        await self.events.start()
        self.pcm.start()
        source_task = (
            asyncio.create_task(self.source.run(), name="sendspin-source")
            if self.source is not None
            else None
        )
        if source_task is not None:
            source_task.add_done_callback(self._on_source_done)
        log.info("Spotify Bridge running for Spotify device '%s'", self.config.name)
        try:
            await self._stopped.wait()
        finally:
            if source_task is not None:
                source_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await source_task

    def _on_source_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        if (err := task.exception()) is not None:
            # e.g. an unreadable identity file: stop, so s6 restarts us and the log shows why.
            log.error("Sendspin source failed: %s", err, exc_info=err)
            self.failed = True
            self.request_stop()

    async def close(self) -> None:
        await self.pcm.stop()
        self.events.close()

    def request_stop(self) -> None:
        self._stopped.set()


async def run(config: Config) -> int:
    """Run until SIGTERM. Returns the process exit code (1 if the source failed)."""
    ha = HomeAssistant()
    source = SendspinSource(
        config.music_assistant_url,
        config.source_name,
        Path(config.state_dir),
        static_pairing_code=config.pairing_code,
        on_pairing_code=ha.show_pairing_code if ha.available else None,
    )
    bridge = Bridge(config, source=source)
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, bridge.request_stop)
    try:
        await bridge.run()
    finally:
        await bridge.close()
        await ha.close()
        log.info("Spotify Bridge stopped")
    return 1 if bridge.failed else 0
