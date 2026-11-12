from spotify_bridge.state import PlayerState, PlayerStateMachine, volume_to_percent


def ev(name: str, **extra: str) -> dict[str, str]:
    return {"PLAYER_EVENT": name, **extra}


def test_starts_idle_without_signal():
    sm = PlayerStateMachine()
    assert sm.snapshot.state is PlayerState.IDLE
    assert not sm.snapshot.signal_present


def test_typical_session():
    sm = PlayerStateMachine()
    sm.apply(ev("session_connected", CLIENT_NAME="Phone"))
    assert sm.snapshot.state is PlayerState.CONNECTED
    assert sm.snapshot.client_name == "Phone"

    sm.apply(ev("track_changed", TRACK_ID="abc", NAME="Light", ARTISTS="A\nB",
                ALBUM="X", DURATION_MS="239853", COVERS="https://c/1\nhttps://c/2"))
    track = sm.snapshot.track
    assert (track.title, track.artists, track.album) == ("Light", ("A", "B"), "X")
    assert track.duration_ms == 239853
    assert track.cover_url == "https://c/1"

    sm.apply(ev("playing", TRACK_ID="abc", POSITION_MS="0"))
    assert sm.snapshot.signal_present

    sm.apply(ev("paused", TRACK_ID="abc"))
    assert sm.snapshot.state is PlayerState.PAUSED
    assert not sm.snapshot.signal_present

    sm.apply(ev("playing", TRACK_ID="abc"))
    sm.apply(ev("session_disconnected"))
    assert sm.snapshot.state is PlayerState.IDLE
    assert sm.snapshot.client_name is None
    assert not sm.snapshot.signal_present


def test_stopped_returns_to_connected():
    sm = PlayerStateMachine()
    sm.apply(ev("session_connected"))
    sm.apply(ev("playing"))
    sm.apply(ev("stopped"))
    assert sm.snapshot.state is PlayerState.CONNECTED


def test_session_connected_does_not_reset_playing():
    sm = PlayerStateMachine()
    sm.apply(ev("playing"))
    sm.apply(ev("session_connected"))
    assert sm.snapshot.state is PlayerState.PLAYING


def test_volume_mapping_and_ignored_events():
    sm = PlayerStateMachine()
    sm.apply(ev("volume_changed", VOLUME="32768"))
    assert sm.snapshot.volume_percent == 50
    before = sm.snapshot
    for name in ("loading", "preloading", "end_of_track", "seeked", "shuffle_changed", "nope"):
        sm.apply(ev(name))
    assert sm.snapshot == before
    sm.apply(ev("volume_changed", VOLUME="garbage"))
    assert sm.snapshot.volume_percent == 50


def test_volume_to_percent_bounds():
    assert volume_to_percent("0") == 0
    assert volume_to_percent("65535") == 100
    assert volume_to_percent("70000") == 100
    assert volume_to_percent("-5") == 0
    assert volume_to_percent(None) is None


def test_listeners_called_only_on_change_and_isolated():
    sm = PlayerStateMachine()
    calls = []

    def bad(old, new):
        raise RuntimeError("boom")

    sm.add_listener(bad)
    sm.add_listener(lambda old, new: calls.append((old.state, new.state)))
    sm.apply(ev("playing"))
    sm.apply(ev("playing"))  # no change, no call
    sm.apply(ev("paused"))
    assert calls == [
        (PlayerState.IDLE, PlayerState.PLAYING),
        (PlayerState.PLAYING, PlayerState.PAUSED),
    ]


def test_sink_status():
    sm = PlayerStateMachine()
    sm.apply(ev("sink", SINK_STATUS="running"))
    assert sm.snapshot.sink_status == "running"
