"""Manual live test of SendspinSource against a real Music Assistant (from any PC).

No librespot: a tone generator stands in for the PCM reader, and a control file
stands in for Spotify's play/pause:

    control.txt = "present" | "absent" | "quit"

    python tests/live_ma_source.py --server ws://<ma-host>:8927/sendspin \
        --state-dir <dir> --pairing-code 12345678

Logs go to stdout. Not run by pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import struct
import time
from pathlib import Path

from spotify_bridge.pcm import CHUNK_FRAMES, CHUNK_MS
from spotify_bridge.sendspin_source import SendspinSource


def tone_chunk(start: float) -> bytes:
    out = bytearray()
    for n in range(CHUNK_FRAMES):
        t = start + n / 44100
        click = 0.6 if (t % 2.0) < 0.06 else 0.0
        v = int(32767 * (0.08 * math.sin(2 * math.pi * 440 * t) + click * math.sin(2 * math.pi * 1000 * t)))
        out += struct.pack("<hh", v, v)
    return bytes(out)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", required=True)
    ap.add_argument("--state-dir", type=Path, required=True)
    ap.add_argument("--pairing-code")
    ap.add_argument("--name", default="Spotify Bridge live test")
    ap.add_argument("--control", type=Path, default=Path("control.txt"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    async def show(code: str | None) -> None:
        print(f"PAIRING CODE FOR MA: {code}" if code else "pairing ended", flush=True)

    source = SendspinSource(args.server, args.name, args.state_dir,
                            static_pairing_code=args.pairing_code, on_pairing_code=show)
    task = asyncio.create_task(source.run())
    loop = asyncio.get_running_loop()
    next_tick = loop.time()
    last = None
    while True:
        ctl = args.control.read_text().strip() if args.control.exists() else "absent"
        if ctl == "quit":
            break
        if ctl != last:
            source.set_signal(ctl == "present")
            last = ctl
        if ctl == "present":  # like librespot: PCM only flows while playing
            await source.feed(tone_chunk(time.time()), next_tick)
        next_tick += CHUNK_MS / 1000
        await asyncio.sleep(max(0.0, next_tick - loop.time()))
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
