"""Entry point: ``spotify-bridge`` (run by the s6 ``bridge`` service)."""

from __future__ import annotations

import asyncio
import logging
import sys

from spotify_bridge.app import run
from spotify_bridge.config import load_config


def main() -> int:
    config = load_config()
    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s] %(levelname)s (%(name)s) %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    asyncio.run(run(config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
