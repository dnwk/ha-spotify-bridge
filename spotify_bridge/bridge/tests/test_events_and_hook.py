import json
import socket
import sys

import pytest

from spotify_bridge import event_hook
from spotify_bridge.events import parse_datagram


def test_build_payload_forwards_known_vars_only():
    payload = event_hook.build_payload(
        {"PLAYER_EVENT": "playing", "TRACK_ID": "x", "PATH": "/bin", "HOME": "/root"}
    )
    assert json.loads(payload) == {"PLAYER_EVENT": "playing", "TRACK_ID": "x"}


def test_build_payload_none_without_event():
    assert event_hook.build_payload({"TRACK_ID": "x"}) is None


def test_build_payload_drops_huge_covers():
    payload = event_hook.build_payload(
        {"PLAYER_EVENT": "track_changed", "NAME": "n", "COVERS": "u" * 100_000}
    )
    assert json.loads(payload) == {"PLAYER_EVENT": "track_changed", "NAME": "n"}


def test_build_payload_keeps_unicode():
    payload = event_hook.build_payload({"PLAYER_EVENT": "track_changed", "NAME": "用背脊唱情歌"})
    assert json.loads(payload)["NAME"] == "用背脊唱情歌"


@pytest.mark.parametrize(
    "data",
    [b"", b"not json", b"[1,2]", b'{"NAME": "x"}', b'{"PLAYER_EVENT": 5}', b"\xff\xfe"],
)
def test_parse_datagram_rejects_malformed(data):
    assert parse_datagram(data) is None


def test_parse_datagram_roundtrip():
    payload = event_hook.build_payload({"PLAYER_EVENT": "paused", "POSITION_MS": "10"})
    assert parse_datagram(payload) == {"PLAYER_EVENT": "paused", "POSITION_MS": "10"}


@pytest.mark.skipif(sys.platform == "win32", reason="needs AF_UNIX datagram sockets")
def test_hook_main_succeeds_when_bridge_is_down(monkeypatch, tmp_path):
    monkeypatch.setenv("PLAYER_EVENT", "playing")
    monkeypatch.setenv("SPOTIFY_BRIDGE_EVENT_SOCKET", str(tmp_path / "missing.sock"))
    assert event_hook.main() == 0


@pytest.mark.skipif(sys.platform == "win32", reason="needs AF_UNIX datagram sockets")
def test_hook_to_event_server(monkeypatch, tmp_path):
    import asyncio

    from spotify_bridge.events import EventServer

    path = str(tmp_path / "events.sock")
    received = []

    # librespot's children inherit its environment; shells often set e.g. NAME.
    for var in event_hook.FORWARDED_VARS:
        monkeypatch.delenv(var, raising=False)

    async def scenario():
        server = EventServer(path, received.append)
        await server.start()
        monkeypatch.setenv("PLAYER_EVENT", "volume_changed")
        monkeypatch.setenv("VOLUME", "65535")
        monkeypatch.setenv("SPOTIFY_BRIDGE_EVENT_SOCKET", path)
        assert event_hook.main() == 0
        for _ in range(50):
            if received:
                break
            await asyncio.sleep(0.01)
        server.close()

    asyncio.run(scenario())
    assert received == [{"PLAYER_EVENT": "volume_changed", "VOLUME": "65535"}]
    assert socket  # keep import used
