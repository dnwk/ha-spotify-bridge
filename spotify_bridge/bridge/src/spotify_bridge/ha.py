"""Home Assistant Core and Supervisor APIs (needs ``homeassistant_api: true``).

All calls go through the Supervisor proxy with ``SUPERVISOR_TOKEN``. Without a
token (local development) every call is a no-op that returns nothing.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
CORE_API = f"{SUPERVISOR_URL}/core/api"
PAIRING_NOTIFICATION_ID = "spotify_bridge_pairing"
# Music Assistant player entities carry this attribute; the bridge's own source does not
# play anything itself, so it is excluded by type.
MA_TYPE_ATTR = "mass_player_type"
ACTIVE_STATES = ("playing", "paused", "buffering", "on")


@dataclass(frozen=True)
class MaPlayer:
    entity_id: str
    name: str
    state: str
    media_content_id: str
    volume_level: float | None


def ma_players_from_states(states: list[dict], exclude_names: tuple[str, ...] = ()) -> list[MaPlayer]:
    """Music Assistant speakers and groups from a ``/api/states`` listing."""
    players = []
    for item in states:
        entity_id = str(item.get("entity_id", ""))
        attrs = item.get("attributes") or {}
        if not entity_id.startswith("media_player.") or MA_TYPE_ATTR not in attrs:
            continue
        if attrs.get(MA_TYPE_ATTR) == "source":
            continue
        name = str(attrs.get("friendly_name") or entity_id)
        if name in exclude_names:
            continue
        volume = attrs.get("volume_level")
        players.append(
            MaPlayer(
                entity_id=entity_id,
                name=name,
                state=str(item.get("state", "")),
                media_content_id=str(attrs.get("media_content_id") or ""),
                volume_level=float(volume) if isinstance(volume, (int, float)) else None,
            )
        )
    return sorted(players, key=lambda p: p.name.casefold())


def players_playing_source(players: list[MaPlayer], source_uri: str) -> list[MaPlayer]:
    """Players whose current media is this source (normally zero or one)."""
    return [p for p in players if p.media_content_id == source_uri and p.state in ACTIVE_STATES]


class HomeAssistant:
    def __init__(self, token: str | None = None, base_url: str = SUPERVISOR_URL) -> None:
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN")
        self._base = base_url
        self._session: aiohttp.ClientSession | None = None

    @property
    def available(self) -> bool:
        return bool(self._token)

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Authorization": f"Bearer {self._token}"},
            )
        return self._session

    async def _get(self, path: str) -> object:
        async with self._http().get(f"{self._base}{path}") as resp:
            if resp.status >= 400:
                raise RuntimeError(f"GET {path}: HTTP {resp.status}")
            return await resp.json()

    async def call_service(self, domain: str, service: str, data: dict[str, object]) -> None:
        if not self._token:
            log.debug("No SUPERVISOR_TOKEN; skipping %s.%s", domain, service)
            return
        url = f"{self._base}/core/api/services/{domain}/{service}"
        async with self._http().post(url, json=data) as resp:
            if resp.status >= 400:
                body = (await resp.text())[:200]
                raise RuntimeError(f"{domain}.{service} failed: HTTP {resp.status} {body}")

    # ----- Music Assistant players -----

    async def ma_players(self, exclude_names: tuple[str, ...] = ()) -> list[MaPlayer]:
        if not self._token:
            return []
        states = await self._get("/core/api/states")
        return ma_players_from_states(states if isinstance(states, list) else [], exclude_names)

    async def play_source(self, entity_id: str, source_uri: str) -> None:
        """Start (or move) the bridge's Live Input on ``entity_id``."""
        await self.call_service(
            "music_assistant", "play_media", {"entity_id": entity_id, "media_id": source_uri}
        )

    async def stop(self, entity_id: str) -> None:
        await self.call_service("media_player", "media_stop", {"entity_id": entity_id})

    async def set_volume(self, entity_id: str, percent: int) -> None:
        level = max(0, min(100, percent)) / 100
        await self.call_service(
            "media_player", "volume_set", {"entity_id": entity_id, "volume_level": level}
        )

    # ----- Supervisor services -----

    async def mqtt_credentials(self) -> dict[str, object] | None:
        """Broker details from the Supervisor (needs ``services: [mqtt:want]``)."""
        if not self._token:
            return None
        try:
            data = await self._get("/services/mqtt")
        except (RuntimeError, aiohttp.ClientError) as err:
            log.info("No MQTT broker from the Supervisor (%s)", err)
            return None
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        return data if isinstance(data, dict) and data.get("host") else None

    # ----- notifications -----

    async def show_pairing_code(self, code: str | None) -> None:
        """Show (or clear, for None) the Music Assistant pairing code as a notification."""
        if code is None:
            await self.call_service(
                "persistent_notification", "dismiss", {"notification_id": PAIRING_NOTIFICATION_ID}
            )
            return
        await self.call_service(
            "persistent_notification",
            "create",
            {
                "notification_id": PAIRING_NOTIFICATION_ID,
                "title": "Spotify Bridge: Music Assistant pairing code",
                "message": (
                    f"Enter **{code}** in Music Assistant to finish setting up the "
                    "Spotify Bridge. The code is valid for about 2 minutes; this "
                    "notification disappears when pairing ends."
                ),
            },
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
