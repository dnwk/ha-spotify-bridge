"""Manual Linux smoke test: the real Bridge with a fake librespot.

Writes 6 s of a 440 Hz tone into a FIFO at real-time speed (like librespot's
pipe backend under back-pressure would) and fires events through the real
``spotify-bridge-event`` hook. Prints the bridge log.

    PYTHONPATH=src python3 tests/smoke_linux.py
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import struct
import subprocess
import sys
import tempfile

from spotify_bridge.app import Bridge
from spotify_bridge.config import Config


def tone(seconds: float) -> bytes:
    frames = int(44100 * seconds)
    out = bytearray()
    for n in range(frames):
        v = int(0.25 * 32767 * math.sin(2 * math.pi * 440 * n / 44100))
        out += struct.pack("<hh", v, v)
    return bytes(out)


def fire(sock: str, **env: str) -> None:
    clean = {k: v for k, v in os.environ.items() if k not in ("NAME",)}
    clean.update(env, SPOTIFY_BRIDGE_EVENT_SOCKET=sock)
    subprocess.run([sys.executable, "-m", "spotify_bridge.event_hook"], env=clean, check=True)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(relativeCreated)6.0f ms %(message)s")
    tmp = tempfile.mkdtemp()
    fifo, sock = f"{tmp}/audio.fifo", f"{tmp}/events.sock"
    os.mkfifo(fifo)
    bridge = Bridge(Config(name="Smoke"), fifo_path=fifo, event_socket_path=sock)
    runner = asyncio.create_task(bridge.run())
    await asyncio.sleep(0.2)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="session_connected",
                                                  CLIENT_NAME="Phone"))
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="track_changed",
                                                  NAME="Test Tone", ARTISTS="Bridge",
                                                  DURATION_MS="6000"))
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="volume_changed",
                                                  VOLUME="45000"))
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="playing"))

    # Writer behaves like librespot: blocking writes, so the reader paces it.
    audio = tone(6.0)

    def write_all() -> float:
        start = loop.time()
        fd = os.open(fifo, os.O_WRONLY)
        view = memoryview(audio)
        while view:
            n = os.write(fd, view[:8192])
            view = view[n:]
        os.close(fd)
        return loop.time() - start

    took = await loop.run_in_executor(None, write_all)
    print(f"writer finished 6.0 s of audio in {took:.2f} s (paced by the reader)")
    await asyncio.sleep(0.5)
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="paused"))
    await loop.run_in_executor(None, lambda: fire(sock, PLAYER_EVENT="session_disconnected"))
    await asyncio.sleep(0.3)
    print("stats:", bridge.pcm.stats)
    bridge.request_stop()
    await runner
    await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
