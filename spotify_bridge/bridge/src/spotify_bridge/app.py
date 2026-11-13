"""Wires the pieces together.

librespot events drive the state machine; its ``signal_present`` becomes the
Sendspin line-sense signal. The PCM reader drains the FIFO in real time and
hands each chunk to the Sendspin source, which forwards it while Music
Assistant is asking for audio.

Home Assistant integration (optional, needs a Supervisor token):

* volume: the Spotify slider is mirrored onto the speaker playing the source;
* speaker: an MQTT "Speaker" select; when it names a speaker, the bridge starts
  (or moves) the Live Input there itself.
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
from spotify_bridge.ha import HomeAssistant, players_playing_source
from spotify_bridge.pcm import CHUNK_MS, PcmReader, level_dbfs
from spotify_bridge.sendspin_source import SendspinSource
from spotify_bridge.speaker_select import SpeakerSelect
from spotify_bridge.state import PlayerState, PlayerStateMachine, Snapshot
from spotify_bridge.volume import VolumeSync

log = logging.getLogger("spotify_bridge")

LEVEL_LOG_INTERVAL_S = 30.0
# After asking Music Assistant to play on the selected speaker, give it this long
# before stopping any other speaker that still plays the source.
MOVE_SETTLE_S = 3.0


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
        ha: HomeAssistant | None = None,
    ) -> None:
        self.config = config
        self.source = source
        self.ha = ha
        self.failed = False
        self.state = PlayerStateMachine()
        self.state.add_listener(self._on_state_change)
        self.events = EventServer(event_socket_path, self.state.apply)
        self.pcm = PcmReader(fifo_path, self._on_chunk)
        self.volume = (
            VolumeSync(self._apply_volume)
            if ha is not None and ha.available and config.volume_sync
            else None
        )
        self.speaker = (
            SpeakerSelect(
                ha,
                self._on_speaker_change,
                device_name=f"Spotify Bridge ({config.name})",
                exclude_names=(config.source_name,),
            )
            if ha is not None and ha.available and config.speaker_select
            else None
        )
        self._tasks: set[asyncio.Task[None]] = set()
        self._target_lock = asyncio.Lock()
        self._chunks_since_log = 0
        self._peak_dbfs = -math.inf
        self._stopped = asyncio.Event()

    # ----- player events -----

    def _on_state_change(self, old: Snapshot, new: Snapshot) -> None:
        if old.state is not new.state or old.track != new.track:
            log.info("Player: %s", describe(new))
        elif old.volume_percent != new.volume_percent:
            log.info("Spotify volume: %s%%", new.volume_percent)

        if self.volume is not None:
            if old.state is PlayerState.IDLE and new.state is not PlayerState.IDLE:
                self.volume.session_started()
            if new.volume_percent is not None and new.volume_percent != old.volume_percent:
                self.volume.on_spotify_volume(new.volume_percent)

        if old.signal_present != new.signal_present:
            log.info("Signal %s", "present" if new.signal_present else "absent")
            if self.source is not None:
                self.source.set_signal(new.signal_present)
            if new.signal_present:
                self._spawn(self._ensure_selected_speaker())

    def _spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ----- Home Assistant: volume and speaker -----

    async def _playing_entities(self) -> list[str]:
        uri = self.source.source_uri if self.source is not None else None
        if self.ha is None or uri is None:
            return []
        players = await self.ha.ma_players()
        return [p.entity_id for p in players_playing_source(players, uri)]

    async def _apply_volume(self, percent: int) -> None:
        targets = await self._playing_entities()
        if not targets:
            log.debug("Spotify volume %s%%: no speaker is playing the bridge", percent)
            return
        for entity_id in targets:
            await self.ha.set_volume(entity_id, percent)
        log.info("Speaker volume set to %s%% (%s)", percent, ", ".join(targets))

    async def _ensure_selected_speaker(self) -> None:
        """Play on the selected speaker; stop the source anywhere else."""
        if self.speaker is None or self.ha is None or self.source is None:
            return
        target = self.speaker.selected_entity
        uri = self.source.source_uri
        if target is None or uri is None:
            return  # "Music Assistant setting": MA's auto-start decides
        async with self._target_lock:
            try:
                playing = await self._playing_entities()
                if target not in playing:
                    log.info("Starting Spotify on %s", target)
                    await self.ha.play_source(target, uri)
                others = [e for e in playing if e != target]
                if others:
                    await asyncio.sleep(MOVE_SETTLE_S)
                    still = [e for e in await self._playing_entities() if e != target]
                    for entity_id in still:
                        log.info("Stopping Spotify on %s (moved to %s)", entity_id, target)
                        await self.ha.stop(entity_id)
            except Exception as err:  # noqa: BLE001 - keep the bridge running
                log.warning("Could not switch to speaker %s: %s", target, err)

    async def _on_speaker_change(self, old: str | None, new: str | None) -> None:
        if new is not None and self.state.snapshot.signal_present:
            await self._ensure_selected_speaker()

    # ----- audio -----

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

    # ----- lifecycle -----

    async def run(self) -> None:
        await self.events.start()
        self.pcm.start()
        background: list[asyncio.Task[None]] = []
        if self.source is not None:
            task = asyncio.create_task(self.source.run(), name="sendspin-source")
            task.add_done_callback(self._on_source_done)
            background.append(task)
        if self.speaker is not None:
            background.append(asyncio.create_task(self.speaker.run(), name="speaker-select"))
        log.info("Spotify Bridge running for Spotify device '%s'", self.config.name)
        try:
            await self._stopped.wait()
        finally:
            for task in (*background, *self._tasks):
                task.cancel()
            for task in (*background, *self._tasks):
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

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
        if self.volume is not None:
            await self.volume.close()

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
    bridge = Bridge(config, source=source, ha=ha)
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
