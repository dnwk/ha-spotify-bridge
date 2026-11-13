"""Home Assistant Core API through the Supervisor proxy (needs ``homeassistant_api: true``)."""

from __future__ import annotations

import logging
import os

import aiohttp

log = logging.getLogger(__name__)

CORE_API = "http://supervisor/core/api"
PAIRING_NOTIFICATION_ID = "spotify_bridge_pairing"


class HomeAssistant:
    def __init__(self, token: str | None = None, base_url: str = CORE_API) -> None:
        self._token = token if token is not None else os.environ.get("SUPERVISOR_TOKEN")
        self._base = base_url
        self._session: aiohttp.ClientSession | None = None

    @property
    def available(self) -> bool:
        return bool(self._token)

    async def call_service(self, domain: str, service: str, data: dict[str, object]) -> None:
        if not self._token:
            log.debug("No SUPERVISOR_TOKEN; skipping %s.%s", domain, service)
            return
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        url = f"{self._base}/services/{domain}/{service}"
        headers = {"Authorization": f"Bearer {self._token}"}
        async with self._session.post(url, json=data, headers=headers) as resp:
            if resp.status >= 400:
                body = (await resp.text())[:200]
                raise RuntimeError(f"{domain}.{service} failed: HTTP {resp.status} {body}")

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
