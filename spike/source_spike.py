"""Phase 0 check 2: Sendspin *source* spike into Music Assistant.

Throwaway test client. It connects to MA's Sendspin server as a source@v1 client
with line_sense, pairs with a dynamic pairing code (printed to the log), and streams
a test signal while MA asks for it:

  * a quiet 440 Hz tone, with a loud 1 kHz "click" (60 ms) at the start of every
    2-second period, aligned to whole seconds of wall-clock time. This lets the
    delay be measured by ear/phone recording against a wall-clock reference.

The line-sense signal is controlled by the file ``control.txt`` next to this script:
``present`` or ``absent`` (anything else = absent). MA's Sendspin Source plugin
auto-starts on the configured target when the signal goes present.

Based on Sendspin/sendspin-jack-bridge (Apache-2.0), adapted to aiosendspin 10.3.

Usage:
    .venv/Scripts/python.exe -I source_spike.py --server ws://<ma-host>:8927/sendspin
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import time
from pathlib import Path

import numpy as np
from aiosendspin.client import PairingSupport, SendspinClient, SourceCapture
from aiosendspin.clock import LoopClock
from aiosendspin.models.player import SupportedAudioFormat
from aiosendspin.models.source import ClientHelloSourceFeatures, ClientHelloSourceSupport
from aiosendspin.models.types import AudioCodec, Roles, SignalState
from aiosendspin.noise.trust_store import FileClientPairingStore

from state import load_identity, lock_state

log = logging.getLogger("spike")

RATE = 44100
CHANNELS = 2
CHUNK_MS = 20
CHUNK_FRAMES = RATE * CHUNK_MS // 1000  # 882
HERE = Path(__file__).resolve().parent
CONTROL = HERE / "control.txt"


def make_chunk(start_wall: float, frames: int) -> bytes:
    """Test signal for ``frames`` samples starting at wall-clock time ``start_wall``."""
    t = start_wall + np.arange(frames) / RATE
    phase_in_period = np.mod(t, 2.0)
    tone = 0.08 * np.sin(2 * math.pi * 440.0 * t)
    click = np.where(phase_in_period < 0.06, 0.6 * np.sin(2 * math.pi * 1000.0 * t), 0.0)
    mono = (tone + click).clip(-1.0, 1.0)
    pcm = (mono * 32767).astype(np.int16)
    return np.repeat(pcm, CHANNELS).tobytes()


class Spike:
    def __init__(self, server: str, name: str, state_dir: Path) -> None:
        self.server = server
        self.name = name
        self.state_dir = state_dir
        self.client: SendspinClient | None = None
        self.capture: SourceCapture | None = None
        self.requested = False
        self.signal: SignalState | None = None
        self.stop = asyncio.Event()

    async def show_code(self, code: str | None, *, grouped: str | None) -> None:
        if code is not None:
            log.warning("PAIRING CODE: %s", grouped or code)
            (HERE / "pairing_code.txt").write_text(f"{grouped or code}\n", encoding="ascii")
        else:
            log.info("Pairing exchange ended")
            (HERE / "pairing_code.txt").unlink(missing_ok=True)

    def on_command(self, payload) -> None:  # ServerCommandPayload
        if payload.source is not None:
            self.requested = payload.source.command == "start"
            log.info("MA requested source %s", payload.source.command)

    def on_disconnect(self) -> None:
        log.warning("Disconnected from MA")
        self.requested = False
        self.stop.set()

    async def run(self) -> None:
        identity = load_identity(self.state_dir)
        store = await FileClientPairingStore.open(self.state_dir / "pairings.json")
        self.client = SendspinClient(
            identity=identity,
            clock=LoopClock(asyncio.get_running_loop()),
            client_name=self.name,
            roles=[Roles.SOURCE],
            pairing_store=store,
            pairing_support=PairingSupport(
                pairing_code_display=self.show_code,
                offer_static_pairing_code=False,
                pair_pending_message="Spotify Bridge spike: the pairing code is in the test log.",
            ),
            source_support=ClientHelloSourceSupport(
                features=ClientHelloSourceFeatures(line_sense=True)
            ),
        )
        self.client.add_server_command_listener(self.on_command)
        self.client.add_disconnect_listener(self.on_disconnect)
        # Headless "pairing gesture": keep a pairing window open while unpaired.
        self.client.open_pairing_window()
        log.info("Connecting to %s as '%s' (client id %s)", self.server, self.name,
                 identity.peer_id)
        await self.client.connect(self.server)
        log.info("Connected/admitted")
        while not self.client.is_time_synchronized():
            if self.stop.is_set():
                return
            await asyncio.sleep(0.1)
        log.info("Time synchronized")
        await self.loop()

    async def set_signal(self, want: SignalState) -> None:
        if want == self.signal:
            return
        conn = self.client._admitted_connection  # noqa: SLF001 (spike only)
        try:
            await conn.send_source_signal(want)
            self.signal = want
            log.info("Signal -> %s", want.value)
        except RuntimeError as err:
            # Source role not active yet (e.g. still unpaired); retry next tick.
            log.debug("Signal not sent yet: %s", err)

    async def loop(self) -> None:
        assert self.client is not None
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        last_status = 0.0
        while not self.stop.is_set():
            ctl = CONTROL.read_text(encoding="ascii").strip() if CONTROL.exists() else ""
            await self.set_signal(SignalState.PRESENT if ctl == "present" else SignalState.ABSENT)

            if self.requested and self.capture is None:
                fmt = SupportedAudioFormat(codec=AudioCodec.PCM, channels=CHANNELS,
                                           sample_rate=RATE, bit_depth=16)
                self.capture = self.client.create_source_capture(fmt)
                await self.capture.start()
                log.info("Streaming started (%s)", self.capture.codec.value)
            elif not self.requested and self.capture is not None:
                cap, self.capture = self.capture, None
                await cap.stop()
                log.info("Streaming stopped")

            if self.capture is not None:
                # Capture timestamp = start of this chunk on the client clock.
                ts_us = self.client.now_us()
                await self.capture.feed(make_chunk(time.time(), CHUNK_FRAMES),
                                        capture_timestamp_us=ts_us)

            if loop.time() - last_status > 10:
                last_status = loop.time()
                log.info("status: signal=%s requested=%s streaming=%s",
                         self.signal and self.signal.value, self.requested,
                         self.capture is not None)

            next_tick += CHUNK_MS / 1000
            await asyncio.sleep(max(0.0, next_tick - loop.time()))

    async def close(self) -> None:
        if self.capture is not None:
            await self.capture.stop()
        if self.client is not None:
            await self.client.disconnect()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--name", default="Spotify Bridge spike")
    ap.add_argument("--state-dir", type=Path, default=HERE / ".state")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    with lock_state(args.state_dir):
        spike = Spike(args.server, args.name, args.state_dir)
        try:
            await spike.run()
        finally:
            await spike.close()


if __name__ == "__main__":
    asyncio.run(main())
