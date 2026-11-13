import asyncio

from spotify_bridge.config import Config
from spotify_bridge.ha import MaPlayer, ma_players_from_states, players_playing_source
from spotify_bridge.speaker_select import OFF_OPTION, build_options, discovery_payload
from spotify_bridge.volume import VolumeSync

URI = "sendspin_source://audio_source/abc"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def run_volume(scenario):
    applied = []

    async def apply(pct):
        applied.append(pct)

    clock = FakeClock()

    async def main():
        sync = VolumeSync(apply, debounce_s=0.05, grace_s=3.0, clock=clock)
        await scenario(sync, clock)
        await asyncio.sleep(0.1)
        await sync.close()

    asyncio.run(main())
    return applied


def test_volume_debounce_applies_last_value_only():
    async def scenario(sync, clock):
        for pct in (10, 20, 30, 42):
            sync.on_spotify_volume(pct)

    assert run_volume(scenario) == [42]


def test_volume_ignored_during_grace_after_session_start():
    async def scenario(sync, clock):
        sync.session_started()
        sync.on_spotify_volume(50)  # Spotify's automatic initial volume
        clock.now += 1.0
        sync.on_spotify_volume(55)  # still in grace
        await asyncio.sleep(0.1)
        clock.now += 5.0
        sync.on_spotify_volume(70)  # user moved the slider

    assert run_volume(scenario) == [70]


def test_volume_same_value_not_reapplied_until_new_session():
    async def scenario(sync, clock):
        sync.on_spotify_volume(30)
        await asyncio.sleep(0.1)
        sync.on_spotify_volume(30)
        await asyncio.sleep(0.1)
        sync.session_started()
        clock.now += 10
        sync.on_spotify_volume(30)

    assert run_volume(scenario) == [30, 30]


def test_volume_apply_failure_is_contained():
    async def boom(pct):
        raise RuntimeError("HA down")

    async def main():
        sync = VolumeSync(boom, debounce_s=0.01)
        sync.on_spotify_volume(10)
        await asyncio.sleep(0.05)
        assert sync.last_applied is None
        await sync.close()

    asyncio.run(main())


STATES = [
    {"entity_id": "media_player.gcc_2", "state": "idle",
     "attributes": {"friendly_name": "GCC", "mass_player_type": "player", "volume_level": 0.2}},
    {"entity_id": "media_player.living_room_display", "state": "playing",
     "attributes": {"friendly_name": "Living Room Display", "mass_player_type": "player",
                    "media_content_id": URI, "volume_level": 0.76}},
    {"entity_id": "media_player.nesthub908b", "state": "playing",
     "attributes": {"friendly_name": "Living Room Display", "media_content_id": URI}},
    {"entity_id": "media_player.spotify_src", "state": "idle",
     "attributes": {"friendly_name": "Spotify (Home Assistant)", "mass_player_type": "source"}},
    {"entity_id": "light.kitchen", "state": "on", "attributes": {"mass_player_type": "player"}},
]


def test_ma_players_filters_non_ma_and_sources():
    players = ma_players_from_states(STATES)
    assert [p.entity_id for p in players] == ["media_player.gcc_2", "media_player.living_room_display"]
    assert players[1].volume_level == 0.76


def test_ma_players_exclude_by_name():
    players = ma_players_from_states(STATES, exclude_names=("GCC",))
    assert [p.name for p in players] == ["Living Room Display"]


def test_players_playing_source_ignores_cast_duplicate():
    players = ma_players_from_states(STATES)
    assert [p.entity_id for p in players_playing_source(players, URI)] == [
        "media_player.living_room_display"
    ]
    assert players_playing_source(players, "sendspin_source://audio_source/other") == []


def test_build_options_disambiguates_duplicate_names():
    players = [
        MaPlayer("media_player.a", "Living Room", "idle", "", None),
        MaPlayer("media_player.b", "Living Room", "idle", "", None),
        MaPlayer("media_player.c", "Kitchen", "idle", "", None),
    ]
    assert build_options(players) == {
        "Living Room (media_player.a)": "media_player.a",
        "Living Room (media_player.b)": "media_player.b",
        "Kitchen": "media_player.c",
    }


def test_discovery_payload_puts_off_option_first():
    payload = discovery_payload(["GCC", "Living Room Display"], "Spotify Bridge (Home Assistant)")
    assert payload["options"] == [OFF_OPTION, "GCC", "Living Room Display"]
    assert payload["unique_id"] == "spotify_bridge_speaker"
    assert payload["device"]["name"] == "Spotify Bridge (Home Assistant)"


def test_config_feature_flags():
    assert Config.from_dict({}).volume_sync is True
    assert Config.from_dict({}).speaker_select is True
    cfg = Config.from_dict({"volume_sync": False, "speaker_select": False})
    assert (cfg.volume_sync, cfg.speaker_select) == (False, False)
    assert Config.from_dict({"volume_sync": "no"}).volume_sync is True  # not a bool: default
