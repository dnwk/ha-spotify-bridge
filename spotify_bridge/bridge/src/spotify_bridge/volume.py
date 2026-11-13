"""Mirror the Spotify volume slider onto the speaker that is playing the bridge.

librespot runs with ``--volume-ctrl fixed`` (full-scale PCM), so the slider in
the Spotify app would otherwise do nothing. Rules:

* Debounce: a slider drag sends many events; only the last value inside
  ``debounce_s`` is applied.
* Grace: Spotify reports a volume when a session starts (always the
  ``initial_volume``). That must not override the speaker's own volume, so
  volume events within ``grace_s`` of a session start are ignored. Same rule
  as Music Assistant's own Spotify Connect plugin.
* Only one direction: the speaker's volume is not reflected back into Spotify
  (librespot has no control API).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

ApplyVolume = Callable[[int], Awaitable[None]]


class VolumeSync:
    def __init__(
        self,
        apply: ApplyVolume,
        *,
        debounce_s: float = 0.3,
        grace_s: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._apply = apply
        self._debounce_s = debounce_s
        self._grace_s = grace_s
        self._clock = clock
        self._session_started_at: float | None = None
        self._pending: int | None = None
        self._task: asyncio.Task[None] | None = None
        self.last_applied: int | None = None

    def session_started(self) -> None:
        """Call when a Spotify session begins (device picked in the app)."""
        self._session_started_at = self._clock()
        self._pending = None
        self.last_applied = None

    def in_grace(self) -> bool:
        started = self._session_started_at
        return started is not None and self._clock() - started < self._grace_s

    def on_spotify_volume(self, percent: int) -> None:
        if self.in_grace():
            log.debug("Ignoring Spotify volume %s%% right after session start", percent)
            return
        self._pending = percent
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._flush())

    async def _flush(self) -> None:
        await asyncio.sleep(self._debounce_s)
        percent, self._pending = self._pending, None
        if percent is None or percent == self.last_applied:
            return
        try:
            await self._apply(percent)
            self.last_applied = percent
        except Exception as err:  # noqa: BLE001 - a failed volume change must not stop the bridge
            log.warning("Could not set speaker volume to %s%%: %s", percent, err)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
