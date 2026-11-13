import json
import logging
import math
import os
import struct
import sys

import pytest

from spotify_bridge.config import Config, load_config
from spotify_bridge.pcm import CHUNK_BYTES, ChunkAssembler, level_dbfs


def test_chunk_size_is_20ms_stereo_s16():
    assert CHUNK_BYTES == 882 * 4


def test_assembler_collects_partial_reads():
    asm = ChunkAssembler(chunk_bytes=8)
    asm.add(b"abc")
    assert asm.take() is None
    assert asm.missing == 5
    asm.add(b"defgh")
    assert asm.take() == b"abcdefgh"
    assert asm.missing == 8


def test_assembler_rejects_overfill():
    asm = ChunkAssembler(chunk_bytes=4)
    with pytest.raises(ValueError):
        asm.add(b"12345")


def test_level_of_silence_and_full_scale():
    assert level_dbfs(b"\x00\x00" * 100) == -math.inf
    full = struct.pack("<h", -32768) * 100
    assert level_dbfs(full) == pytest.approx(0.0, abs=1e-6)
    half = struct.pack("<h", 16384) * 100
    assert level_dbfs(half) == pytest.approx(-6.02, abs=0.01)


def test_config_defaults_when_missing(tmp_path):
    assert load_config(str(tmp_path / "nope.json")) == Config()


def test_config_from_options(tmp_path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps({"name": "Kitchen", "log_level": "debug", "bitrate": 320}))
    cfg = load_config(str(path))
    assert cfg.name == "Kitchen"
    assert cfg.log_level == logging.DEBUG


@pytest.mark.skipif(sys.platform == "win32", reason="needs a real FIFO")
def test_reader_paces_fifo(tmp_path):
    """librespot writes 1 s of audio at once; the reader must take ~50 chunks/s."""
    import asyncio

    from spotify_bridge.pcm import PcmReader

    fifo = str(tmp_path / "audio.fifo")
    os.mkfifo(fifo)
    chunks = []

    async def scenario():
        reader = PcmReader(fifo, lambda c, t: chunks.append(t))
        reader.start()
        writer = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        os.write(writer, b"\x01\x00" * (CHUNK_BYTES // 2) * 15)  # 300 ms, fits the pipe
        await asyncio.sleep(0.2)
        taken_after_200ms = len(chunks)
        await asyncio.sleep(0.3)
        os.close(writer)
        await reader.stop()
        return taken_after_200ms

    taken_after_200ms = asyncio.run(scenario())
    # Paced: about 10 chunks in 200 ms, not all 15 at once.
    assert 8 <= taken_after_200ms <= 13
    assert len(chunks) == 15


def test_config_sendspin_defaults():
    cfg = Config.from_dict({"name": "Home Assistant"})
    assert cfg.music_assistant_url == "ws://localhost:8927/sendspin"
    assert cfg.source_name == "Spotify (Home Assistant)"
    assert cfg.pairing_code is None


def test_config_pairing_code_normalised_and_validated():
    assert Config.from_dict({"pairing_code": "1234-5678"}).pairing_code == "12345678"
    assert Config.from_dict({"pairing_code": " 1234 5678 "}).pairing_code == "12345678"
    assert Config.from_dict({"pairing_code": "123456"}).pairing_code is None
    assert Config.from_dict({"pairing_code": "abcdefgh"}).pairing_code is None


def test_config_custom_names_and_url():
    cfg = Config.from_dict(
        {"name": "Den", "sendspin_name": "Den Spotify", "music_assistant_url": "ws://ma:8927/sendspin"}
    )
    assert cfg.source_name == "Den Spotify"
    assert cfg.music_assistant_url == "ws://ma:8927/sendspin"
