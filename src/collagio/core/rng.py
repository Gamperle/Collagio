"""Seeded, platform-independent random number generators.

Every random decision is drawn from an RNG derived from the project seed plus a
purpose key (e.g. "layout" or a photo id), never from the global RNG. That keeps
results reproducible and independent of the order in which parts are rendered.
"""

from __future__ import annotations

import hashlib
import random


def derive_seed(seed: int, *keys: str | int) -> int:
    material = "\x1f".join(str(part) for part in (seed, *keys)).encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def derive_rng(seed: int, *keys: str | int) -> random.Random:
    return random.Random(derive_seed(seed, *keys))
