"""Persistent Sendspin client identity (the key Music Assistant pairs with).

Adapted from Sendspin/sendspin-jack-bridge ``state.py`` (Apache-2.0).
Losing this file means re-pairing in Music Assistant, so it is never replaced
silently: an unreadable file is an error, not a reason to generate a new key.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from aiosendspin.noise.keys import Identity, b64url_decode


def load_identity(state_dir: Path) -> Identity:
    """Load ``identity.key`` from ``state_dir``, creating it atomically on first run."""
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = state_dir / "identity.key"
    try:
        encoded = path.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        identity = Identity.generate()
        fd, tmp = tempfile.mkstemp(dir=state_dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write((identity.private_b64u + "\n").encode("ascii"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return identity
    except UnicodeError:
        raise ValueError(f"Invalid identity file {path}; restore it or delete it to re-pair") from None

    try:
        identity = Identity.from_private_bytes(b64url_decode(encoded))
    except ValueError:
        raise ValueError(f"Invalid identity file {path}; restore it or delete it to re-pair") from None
    if identity.private_b64u != encoded:
        raise ValueError(f"Invalid identity file {path}; restore it or delete it to re-pair")
    return identity
