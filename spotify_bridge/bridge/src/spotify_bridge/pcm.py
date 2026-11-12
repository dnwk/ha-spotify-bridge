"""Real-time paced reader for librespot's PCM FIFO.

librespot's pipe backend writes as fast as the reader consumes, so the reader
is the clock: every ``CHUNK_MS`` it takes exactly one chunk from the FIFO.
Whatever is not taken stays in the kernel pipe buffer (64 KiB, about 370 ms
of audio), which then blocks librespot. That back-pressure keeps Spotify's
progress bar in step with real time and keeps latency low.

The FIFO is opened read-write and non-blocking: opening never waits for a
writer, and reads never see EOF when librespot closes its end between tracks.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from array import array
from collections.abc import Callable
from dataclasses import dataclass

from spotify_bridge import FRAME_BYTES, SAMPLE_RATE

log = logging.getLogger(__name__)

CHUNK_MS = 20
CHUNK_FRAMES = SAMPLE_RATE * CHUNK_MS // 1000  # 882
CHUNK_BYTES = CHUNK_FRAMES * FRAME_BYTES  # 3528
# If the loop falls further behind than this, skip ahead instead of bursting.
MAX_CATCH_UP_CHUNKS = 10

ChunkCallback = Callable[[bytes, float], None]


def level_dbfs(chunk: bytes) -> float:
    """RMS level of interleaved s16le PCM in dBFS (-inf for digital silence)."""
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return -math.inf
    mean_square = sum(s * s for s in samples) / len(samples)
    if mean_square == 0:
        return -math.inf
    return 10 * math.log10(mean_square / (32768.0 * 32768.0))


class ChunkAssembler:
    """Accumulates partial reads into fixed-size chunks."""

    def __init__(self, chunk_bytes: int = CHUNK_BYTES) -> None:
        self.chunk_bytes = chunk_bytes
        self._buffer = bytearray()

    @property
    def missing(self) -> int:
        """Bytes still needed to complete the current chunk."""
        return self.chunk_bytes - len(self._buffer)

    def add(self, data: bytes) -> None:
        if len(data) > self.missing:
            raise ValueError("add() got more data than the current chunk needs")
        self._buffer += data

    def take(self) -> bytes | None:
        """Return a complete chunk and start a new one, or None if incomplete."""
        if len(self._buffer) < self.chunk_bytes:
            return None
        chunk = bytes(self._buffer)
        self._buffer.clear()
        return chunk

    def discard(self) -> int:
        dropped = len(self._buffer)
        self._buffer.clear()
        return dropped


@dataclass
class PcmStats:
    chunks: int = 0
    starved_ticks: int = 0
    skipped_chunks: int = 0


class PcmReader:
    """Reads the FIFO in real time and hands each chunk to ``on_chunk``."""

    def __init__(self, path: str, on_chunk: ChunkCallback) -> None:
        self._path = path
        self._on_chunk = on_chunk
        self._assembler = ChunkAssembler()
        self._fd: int | None = None
        self._task: asyncio.Task[None] | None = None
        self.stats = PcmStats()
        self.last_data_time: float | None = None

    def start(self) -> None:
        # O_RDWR on a FIFO is Linux-specific but well defined there: we are our
        # own writer, so open() does not block and read() never returns EOF.
        self._fd = os.open(self._path, os.O_RDWR | os.O_NONBLOCK)
        self._task = asyncio.get_running_loop().create_task(self._run(), name="pcm-reader")
        log.info("Reading PCM from %s (%d ms chunks)", self._path, CHUNK_MS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _read_one_chunk(self) -> bytes | None:
        assert self._fd is not None
        while self._assembler.missing:
            try:
                data = os.read(self._fd, self._assembler.missing)
            except BlockingIOError:
                return None
            if not data:  # cannot happen with O_RDWR, but never spin on it
                return None
            self._assembler.add(data)
        return self._assembler.take()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        period = CHUNK_MS / 1000
        next_tick = loop.time()
        while True:
            now = loop.time()
            due = int((now - next_tick) // period) + 1
            if due > MAX_CATCH_UP_CHUNKS:
                self.stats.skipped_chunks += due - 1
                next_tick = now
                due = 1
            for i in range(due):
                tick_time = next_tick + i * period
                chunk = self._read_one_chunk()
                if chunk is None:
                    self.stats.starved_ticks += 1
                    continue
                self.stats.chunks += 1
                self.last_data_time = now
                try:
                    self._on_chunk(chunk, tick_time)
                except Exception:
                    log.exception("PCM chunk handler failed")
            next_tick += due * period
            await asyncio.sleep(max(0.0, next_tick - loop.time()))
