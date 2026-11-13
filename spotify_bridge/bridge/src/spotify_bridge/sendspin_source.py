"""Sendspin *source* client: makes the bridge a Live Input in Music Assistant.

Lifecycle (proven by the Phase 0 spike, see docs/TESTING.md):

1. Dial Music Assistant's Sendspin server (client-initiated, so no inbound port).
2. Until paired, keep a pairing window open. Music Assistant shows the device as
   "requires setup"; the user types the pairing code there. The code is either a
   static 8-digit code from the add-on options, or a dynamic 6-digit code that is
   shown through ``on_pairing_code`` (log + Home Assistant notification).
3. Report line-sense: ``present`` while Spotify plays, ``absent`` otherwise.
   Music Assistant auto-starts the source on its configured target player.
4. Stream PCM only between the server's ``source start`` and ``source stop``.
5. Reconnect with back-off; the pairing survives in ``state_dir``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from aiosendspin.client import PairingSupport, SendspinClient, SourceCapture
from aiosendspin.clock import LoopClock
from aiosendspin.models.player import SupportedAudioFormat
from aiosendspin.models.source import ClientHelloSourceFeatures, ClientHelloSourceSupport
from aiosendspin.models.types import AudioCodec, Roles, SignalState
from aiosendspin.noise.trust_store import FileClientPairingStore

from spotify_bridge import CHANNELS, SAMPLE_RATE
from spotify_bridge.identity import load_identity

log = logging.getLogger(__name__)

PairingCodeCallback = Callable[[str | None], Awaitable[None]]

RECONCILE_INTERVAL_S = 0.5
# aiosendspin closes a pairing window after 300 s; reopen well before that.
PAIRING_WINDOW_REFRESH_S = 240.0
BACKOFF_INITIAL_S = 2.0
BACKOFF_MAX_S = 30.0


class SendspinSource:
    def __init__(
        self,
        server_url: str,
        name: str,
        state_dir: Path,
        *,
        static_pairing_code: str | None = None,
        on_pairing_code: PairingCodeCallback | None = None,
    ) -> None:
        self._url = server_url
        self._name = name
        self._state_dir = state_dir
        self._static_code = static_pairing_code
        self._on_pairing_code = on_pairing_code

        self._client: SendspinClient | None = None
        self._store: FileClientPairingStore | None = None
        self._capture: SourceCapture | None = None
        self._capture_lock = asyncio.Lock()
        self._wake = asyncio.Event()
        self._disconnected = asyncio.Event()

        self._want_signal = SignalState.ABSENT
        self._sent_signal: SignalState | None = None
        self._requested = False
        self._paired = False
        self._window_opened_at: float | None = None
        self.client_id: str | None = None

    # ----- called by the rest of the bridge -----

    def set_signal(self, present: bool) -> None:
        self._want_signal = SignalState.PRESENT if present else SignalState.ABSENT
        self._wake.set()

    async def feed(self, chunk: bytes, tick_time: float) -> None:
        """Send one PCM chunk if Music Assistant is currently asking for audio."""
        if self._capture is None:
            return
        async with self._capture_lock:
            capture = self._capture
            if capture is None:
                return
            try:
                # The reader's tick time is loop time; LoopClock uses the same clock.
                await capture.feed(chunk, capture_timestamp_us=int(tick_time * 1_000_000))
            except (RuntimeError, ConnectionError) as err:
                log.info("Stream to Music Assistant ended: %s", err)
                self._capture = None

    @property
    def streaming(self) -> bool:
        return self._capture is not None

    @property
    def source_uri(self) -> str | None:
        """Music Assistant media id of this Live Input (known once ``run`` started)."""
        return f"sendspin_source://audio_source/{self.client_id}" if self.client_id else None

    # ----- main loop -----

    async def run(self) -> None:
        identity = load_identity(self._state_dir)
        self.client_id = identity.peer_id
        self._store = await FileClientPairingStore.open(self._state_dir / "pairings.json")
        await self._apply_static_code()
        self._paired = bool(await self._store.list_records())

        loop = asyncio.get_running_loop()
        self._client = SendspinClient(
            identity=identity,
            clock=LoopClock(loop),
            client_name=self._name,
            roles=[Roles.SOURCE],
            pairing_store=self._store,
            pairing_support=self._pairing_support(),
            source_support=ClientHelloSourceSupport(
                features=ClientHelloSourceFeatures(line_sense=True)
            ),
        )
        self._client.add_server_command_listener(self._on_server_command)
        self._client.add_disconnect_listener(self._on_disconnect)
        log.info(
            "Sendspin source '%s' (client id %s), %s",
            self._name,
            identity.peer_id,
            "paired" if self._paired else "not paired yet",
        )

        backoff = BACKOFF_INITIAL_S
        try:
            while True:
                try:
                    await self._session()
                    backoff = BACKOFF_INITIAL_S
                except asyncio.CancelledError:
                    raise
                except Exception as err:  # noqa: BLE001 - keep retrying whatever happened
                    log.warning("Music Assistant at %s: %s; retrying in %.0f s",
                                self._url, err, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX_S)
        finally:
            await self._close()

    async def _session(self) -> None:
        assert self._client is not None
        self._disconnected.clear()
        self._sent_signal = None
        self._requested = False
        self._open_pairing_window_if_needed(force=True)
        await self._client.connect(self._url)
        log.info("Connected to Music Assistant at %s", self._url)
        while not self._client.is_time_synchronized():
            if self._disconnected.is_set():
                return
            await asyncio.sleep(0.1)
        while not self._disconnected.is_set():
            await self._reconcile()
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), RECONCILE_INTERVAL_S)
        log.warning("Disconnected from Music Assistant")

    async def _reconcile(self) -> None:
        assert self._client is not None and self._store is not None
        paired = bool(await self._store.list_records())
        if paired != self._paired:
            self._paired = paired
            # Unpairing in Music Assistant removes the record; offer pairing again.
            log.info("Paired with Music Assistant" if paired else "No longer paired")
            if not paired:
                self._window_opened_at = None
        self._open_pairing_window_if_needed()

        if self._sent_signal is not self._want_signal:
            connection = self._client._admitted_connection  # private: aiosendspin has no public accessor
            if connection is not None:
                try:
                    await connection.send_source_signal(self._want_signal)
                    self._sent_signal = self._want_signal
                    log.info("Told Music Assistant: signal %s", self._want_signal.value)
                except RuntimeError as err:
                    # Source role inactive until paired; retried on the next pass.
                    log.debug("Signal not sent yet: %s", err)

        async with self._capture_lock:
            if self._requested and self._capture is None:
                fmt = SupportedAudioFormat(
                    codec=AudioCodec.PCM, channels=CHANNELS, sample_rate=SAMPLE_RATE, bit_depth=16
                )
                capture = self._client.create_source_capture(fmt)
                await capture.start()
                self._capture = capture
                log.info("Streaming to Music Assistant (%s)", capture.codec.value)
            elif not self._requested and self._capture is not None:
                capture, self._capture = self._capture, None
                with contextlib.suppress(RuntimeError, ConnectionError):
                    await capture.stop()
                log.info("Stopped streaming to Music Assistant")

    # ----- pairing -----

    async def _apply_static_code(self) -> None:
        """Offer exactly one pairing-code method: the static code if set, else dynamic.

        aiosendspin only advertises ``static_pairing_code`` when the store's pairing
        config enables it (off by default); without that, Music Assistant falls back
        to asking for a long pairing token.
        """
        assert self._store is not None
        current = await self._store.get_pairing_config()
        if self._static_code:
            await self._store.set_static_pairing_code(self._static_code)
        else:
            await self._store.clear_static_pairing_code()
        wanted = replace(
            current,
            static_pairing_code_enabled=bool(self._static_code),
            dynamic_pairing_code_enabled=not self._static_code,
        )
        if wanted != current:
            await self._store.store_pairing_config(wanted)

    def _pairing_support(self) -> PairingSupport:
        message = (
            "Enter the 8-digit pairing code from the Spotify Bridge app settings."
            if self._static_code
            else "The pairing code is shown in Home Assistant notifications."
        )
        if self._static_code:
            # A pairing-code display would switch to dynamic codes, so offer none.
            return PairingSupport(
                offer_static_pairing_code=True,
                secret_locations=("operator",),
                pair_pending_message=message,
            )
        return PairingSupport(
            pairing_code_display=self._show_code,
            offer_static_pairing_code=False,
            pair_pending_message=message,
        )

    def _open_pairing_window_if_needed(self, *, force: bool = False) -> None:
        if self._paired or self._client is None:
            return
        now = asyncio.get_running_loop().time()
        if force or self._window_opened_at is None or (
            now - self._window_opened_at > PAIRING_WINDOW_REFRESH_S
        ):
            # Headless device: opening the window is our "pairing gesture".
            self._client.open_pairing_window()
            self._window_opened_at = now

    async def _show_code(self, pairing_code: str | None, *, grouped: str | None) -> None:
        if pairing_code is not None:
            log.warning("Music Assistant pairing code: %s", grouped or pairing_code)
        else:
            log.info("Pairing exchange ended")
        if self._on_pairing_code is not None:
            try:
                await self._on_pairing_code(grouped or pairing_code)
            except Exception:
                log.exception("Could not show the pairing code in Home Assistant")

    # ----- aiosendspin callbacks (sync) -----

    def _on_server_command(self, payload) -> None:  # ServerCommandPayload
        if payload.source is not None:
            self._requested = payload.source.command == "start"
            log.info("Music Assistant requested source %s", payload.source.command)
            self._wake.set()

    def _on_disconnect(self) -> None:
        self._requested = False
        self._capture = None  # bound to the connection that just ended
        self._disconnected.set()
        self._wake.set()

    async def _close(self) -> None:
        if self._capture is not None:
            with contextlib.suppress(Exception):
                await self._capture.stop()
            self._capture = None
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
