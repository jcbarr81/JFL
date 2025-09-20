from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SeedManager:
    """Deterministically map identifying information to RNG seeds."""

    base_seed: int = 0

    def game_seed(self, season_label: str, week: int, home_id: str, away_id: str) -> int:
        key = f"{season_label}|{week}|{home_id}|{away_id}|{self.base_seed}"
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, byteorder="big", signed=False)
        # Clamp to 31-bit positive integer for compatibility with Random
        return value % (2**31 - 1) or 1


__all__ = ["SeedManager"]
