"""Phase 4: a "Speaker" select entity in Home Assistant (MQTT discovery).

Options are the Music Assistant speakers/groups Home Assistant knows, plus
``OFF_OPTION`` ("Music Assistant setting"), which leaves the choice to Music
Assistant's "Automatically play line-in on" setting.

With a speaker selected, the bridge starts Spotify on it when playback begins,
and moves it when the selection changes mid-song (see ``app.Bridge``). For
that to be reliable, Music Assistant's own auto-start for this input must be
Off; otherwise both would start a speaker at the same moment.

The selection is stored as a retained MQTT message, so it survives restarts.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence

from spotify_bridge.ha import HomeAssistant, MaPlayer

log = logging.getLogger(__name__)

OFF_OPTION = "Music Assistant setting"
TOPIC_PREFIX = "spotify_bridge"
DISCOVERY_TOPIC = f"homeassistant/select/{TOPIC_PREFIX}/speaker/config"
STATE_TOPIC = f"{TOPIC_PREFIX}/speaker/state"
COMMAND_TOPIC = f"{TOPIC_PREFIX}/speaker/set"
AVAILABILITY_TOPIC = f"{TOPIC_PREFIX}/availability"
REFRESH_S = 60.0
# How long to wait for the retained state (the saved selection) after subscribing.
RESTORE_WINDOW_S = 1.5
RECONNECT_S = 10.0

ChangeCallback = Callable[[str | None, str | None], Awaitable[None]]


def build_options(players: Sequence[MaPlayer]) -> dict[str, str]:
    """Map option label -> entity_id. Duplicate names get the entity id appended."""
    counts: dict[str, int] = {}
    for p in players:
        counts[p.name] = counts.get(p.name, 0) + 1
    options: dict[str, str] = {}
    for p in players:
        label = p.name if counts[p.name] == 1 else f"{p.name} ({p.entity_id})"
        options[label] = p.entity_id
    return options


def discovery_payload(option_labels: Sequence[str], device_name: str) -> dict[str, object]:
    return {
        "name": "Speaker",
        "unique_id": f"{TOPIC_PREFIX}_speaker",
        "object_id": f"{TOPIC_PREFIX}_speaker",
        "icon": "mdi:speaker",
        "command_topic": COMMAND_TOPIC,
        "state_topic": STATE_TOPIC,
        "availability_topic": AVAILABILITY_TOPIC,
        "options": [OFF_OPTION, *option_labels],
        "device": {
            "identifiers": [TOPIC_PREFIX],
            "name": device_name,
            "manufacturer": "Spotify Bridge app",
            "model": "librespot + Sendspin source",
        },
    }


class SpeakerSelect:
    def __init__(
        self,
        ha: HomeAssistant,
        on_change: ChangeCallback,
        *,
        device_name: str = "Spotify Bridge",
        exclude_names: tuple[str, ...] = (),
    ) -> None:
        self._ha = ha
        self._on_change = on_change
        self._device_name = device_name
        self._exclude = exclude_names
        self._options: dict[str, str] = {}
        self._selected_label = OFF_OPTION
        self._published_options: list[str] | None = None
        self._restoring = True

    @property
    def selected_entity(self) -> str | None:
        """Entity to play on, or None when Music Assistant decides."""
        return self._options.get(self._selected_label)

    @property
    def selected_label(self) -> str:
        return self._selected_label

    async def run(self) -> None:
        creds = await self._ha.mqtt_credentials()
        if creds is None:
            log.info("No MQTT broker; the Speaker select entity is not available")
            return
        import aiomqtt  # imported here so the rest of the bridge works without it

        while True:
            try:
                async with aiomqtt.Client(
                    hostname=str(creds["host"]),
                    port=int(creds.get("port", 1883)),
                    username=creds.get("username") or None,
                    password=creds.get("password") or None,
                    identifier=f"{TOPIC_PREFIX}_bridge",
                    will=aiomqtt.Will(AVAILABILITY_TOPIC, "offline", retain=True),
                ) as client:
                    log.info("MQTT connected; publishing the Speaker select entity")
                    self._published_options = None
                    self._restoring = True
                    # Subscribe before publishing anything: the retained state message
                    # carries the last selection and must be read, not overwritten.
                    await client.subscribe(STATE_TOPIC)
                    await client.subscribe(COMMAND_TOPIC)
                    await self._refresh_options(client)
                    await client.publish(AVAILABILITY_TOPIC, "online", retain=True)
                    refresher = asyncio.create_task(self._refresh_loop(client))
                    try:
                        async for message in client.messages:
                            await self._handle(client, str(message.topic), message.payload)
                    finally:
                        refresher.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await refresher
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - reconnect on any MQTT failure
                log.warning("MQTT: %s; reconnecting in %.0f s", err, RECONNECT_S)
                await asyncio.sleep(RECONNECT_S)

    async def _refresh_loop(self, client) -> None:
        await asyncio.sleep(RESTORE_WINDOW_S)
        self._restoring = False
        await client.publish(STATE_TOPIC, self._selected_label, retain=True)
        while True:
            await asyncio.sleep(REFRESH_S)
            try:
                await self._refresh_options(client)
            except Exception as err:  # noqa: BLE001
                log.warning("Could not refresh the speaker list: %s", err)

    async def _refresh_options(self, client) -> None:
        players = await self._ha.ma_players(self._exclude)
        self._options = build_options(players)
        labels = list(self._options)
        if labels != self._published_options:
            payload = discovery_payload(labels, self._device_name)
            await client.publish(DISCOVERY_TOPIC, json.dumps(payload), retain=True)
            self._published_options = labels
            log.info("Speaker options: %s", ", ".join([OFF_OPTION, *labels]))
            if not self._restoring:
                # Re-publish the state so HA shows it against the new option list.
                await client.publish(STATE_TOPIC, self._selected_label, retain=True)

    async def _handle(self, client, topic: str, payload: object) -> None:
        label = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload)
        label = label.strip()
        if topic == STATE_TOPIC:
            # Our own retained state: restore the selection after a restart.
            if label != self._selected_label and (label == OFF_OPTION or label in self._options):
                self._selected_label = label
                log.info("Speaker selection restored: %s", label)
            return
        if topic != COMMAND_TOPIC:
            return
        if label != OFF_OPTION and label not in self._options:
            log.warning("Unknown speaker option %r ignored", label)
            return
        old_entity = self.selected_entity
        self._selected_label = label
        await client.publish(STATE_TOPIC, label, retain=True)
        log.info("Speaker selected: %s", label)
        try:
            await self._on_change(old_entity, self.selected_entity)
        except Exception:
            log.exception("Applying the speaker selection failed")
