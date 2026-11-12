"""Player state machine driven by librespot events.

Pure logic, no I/O, so it can be unit-tested anywhere.

States:
    IDLE       no Spotify Connect session (nobody has picked this device)
    CONNECTED  a session exists, nothing playing (stopped / between contexts)
    PLAYING    audio is being played
    PAUSED     paused by the user

``signal_present`` (what the Sendspin source reports to Music Assistant as
line-sense in Phase 2) is True only while PLAYING.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

log = logging.getLogger(__name__)

# librespot reports volume as 0..65535.
LIBRESPOT_VOLUME_MAX = 65535


class PlayerState(Enum):
    IDLE = "idle"
    CONNECTED = "connected"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True)
class TrackInfo:
    track_id: str = ""
    title: str = ""
    artists: tuple[str, ...] = ()
    album: str = ""
    duration_ms: int | None = None
    cover_url: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """Everything the rest of the bridge needs to know, as one immutable value."""

    state: PlayerState = PlayerState.IDLE
    track: TrackInfo = field(default_factory=TrackInfo)
    volume_percent: int | None = None
    client_name: str | None = None
    sink_status: str | None = None

    @property
    def signal_present(self) -> bool:
        return self.state is PlayerState.PLAYING


def _split_lines(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part for part in value.split("\n") if part)


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def volume_to_percent(raw: str | None) -> int | None:
    value = _int_or_none(raw)
    if value is None:
        return None
    value = max(0, min(LIBRESPOT_VOLUME_MAX, value))
    return round(value * 100 / LIBRESPOT_VOLUME_MAX)


class PlayerStateMachine:
    """Applies librespot events and notifies listeners when the snapshot changes."""

    def __init__(self) -> None:
        self._snapshot = Snapshot()
        self._listeners: list[Callable[[Snapshot, Snapshot], None]] = []

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    def add_listener(self, callback: Callable[[Snapshot, Snapshot], None]) -> None:
        """``callback(old, new)`` is called after every change."""
        self._listeners.append(callback)

    def apply(self, event: dict[str, str]) -> Snapshot:
        """Apply one event (the hook's JSON payload) and return the new snapshot."""
        name = event.get("PLAYER_EVENT", "")
        old = self._snapshot
        new = self._reduce(old, name, event)
        if new != old:
            self._snapshot = new
            for callback in self._listeners:
                try:
                    callback(old, new)
                except Exception:  # a listener must never break event handling
                    log.exception("State listener failed")
        return self._snapshot

    @staticmethod
    def _reduce(old: Snapshot, name: str, event: dict[str, str]) -> Snapshot:
        match name:
            case "session_connected":
                state = old.state if old.state is not PlayerState.IDLE else PlayerState.CONNECTED
                return replace(old, state=state, client_name=event.get("CLIENT_NAME") or None)
            case "session_client_changed":
                return replace(old, client_name=event.get("CLIENT_NAME") or old.client_name)
            case "session_disconnected":
                # Another device was chosen in Spotify, or the session ended.
                return replace(old, state=PlayerState.IDLE, client_name=None)
            case "playing":
                return replace(old, state=PlayerState.PLAYING)
            case "paused":
                return replace(old, state=PlayerState.PAUSED)
            case "stopped":
                return replace(old, state=PlayerState.CONNECTED)
            case "track_changed":
                covers = _split_lines(event.get("COVERS"))
                track = TrackInfo(
                    track_id=event.get("TRACK_ID", ""),
                    title=event.get("NAME", ""),
                    artists=_split_lines(event.get("ARTISTS")) or _split_lines(
                        event.get("SHOW_NAME")
                    ),
                    album=event.get("ALBUM", ""),
                    duration_ms=_int_or_none(event.get("DURATION_MS")),
                    cover_url=covers[0] if covers else None,
                )
                return replace(old, track=track)
            case "volume_changed":
                percent = volume_to_percent(event.get("VOLUME"))
                return old if percent is None else replace(old, volume_percent=percent)
            case "sink":
                return replace(old, sink_status=event.get("SINK_STATUS") or None)
            case _:
                # loading, preloading, end_of_track, seeked, shuffle_changed, ... :
                # no state change for the bridge.
                return old
