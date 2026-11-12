"""librespot ``--onevent`` hook: forward one player event to the bridge.

librespot runs this program once per event, with the event in environment
variables (``PLAYER_EVENT``, ``NAME``, ``VOLUME`` ...), and waits for it to
exit. It must be quick and must never fail loudly: it sends one JSON datagram
to the bridge's Unix socket and exits 0, even if the bridge is not running.

Only the standard library is imported, to keep start-up fast.
"""

from __future__ import annotations

import json
import os
import socket
import sys

from spotify_bridge import EVENT_SOCKET_PATH

# Variables librespot 0.8.0 sets (src/player_event_handler.rs). Unknown ones are ignored.
# The hook inherits librespot's environment too, so a variable can be present on
# an event that does not set it (e.g. a NAME from the shell). The state machine
# only reads each field on the event that defines it (NAME on track_changed, ...).
FORWARDED_VARS = (
    "PLAYER_EVENT",
    "TRACK_ID",
    "URI",
    "NAME",
    "ARTISTS",
    "ALBUM",
    "ALBUM_ARTISTS",
    "SHOW_NAME",
    "COVERS",
    "DURATION_MS",
    "POSITION_MS",
    "VOLUME",
    "SINK_STATUS",
    "CLIENT_ID",
    "CLIENT_NAME",
    "CLIENT_BRAND_NAME",
    "CLIENT_MODEL_NAME",
    "USER_NAME",
    "CONNECTION_ID",
    "ITEM_TYPE",
    "SHUFFLE",
    "REPEAT",
    "REPEAT_TRACK",
    "AUTO_PLAY",
)

# Datagram size limit on Linux Unix sockets is large; keep well below it anyway.
MAX_DATAGRAM = 32 * 1024


def build_payload(environ: dict[str, str]) -> bytes | None:
    """Return the JSON datagram for this event, or None if there is no event."""
    if not environ.get("PLAYER_EVENT"):
        return None
    data = {key: environ[key] for key in FORWARDED_VARS if key in environ}
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    if len(payload) > MAX_DATAGRAM and "COVERS" in data:
        data.pop("COVERS")
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return payload[:MAX_DATAGRAM]


def main() -> int:
    payload = build_payload(dict(os.environ))
    if payload is None:
        return 0
    path = os.environ.get("SPOTIFY_BRIDGE_EVENT_SOCKET", EVENT_SOCKET_PATH)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.5)
            sock.sendto(payload, path)
    except OSError as err:
        # Bridge not running (yet). librespot only logs a warning on non-zero
        # exit, so stay quiet and succeed.
        print(f"spotify-bridge-event: bridge not reachable: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
