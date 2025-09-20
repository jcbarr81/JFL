from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from random import Random
from typing import Optional


class PenaltyType(Enum):
    OFFSIDES = 5
    HOLDING = 10
    DPI = 15


@dataclass
class PenaltyResult:
    accepted: bool
    yards: int
    automatic_first: bool = False


@dataclass
class KickOutcome:
    made: bool
    yards: int


def apply_penalty(penalty: PenaltyType, *, accept: bool = True) -> PenaltyResult:
    if not accept:
        return PenaltyResult(False, 0)
    if penalty == PenaltyType.DPI:
        return PenaltyResult(True, penalty.value, automatic_first=True)
    return PenaltyResult(True, penalty.value, automatic_first=False)


def attempt_field_goal(yardline: float, kicker_rating: int, rng: Optional[Random] = None) -> KickOutcome:
    random = rng or Random()
    distance = max(20.0, 100.0 - yardline + 17.0)
    if distance < 40:
        base_prob = 0.845
    elif distance < 50:
        base_prob = 0.75
    else:
        base_prob = 0.60
    probability = max(0.1, min(0.99, base_prob + (kicker_rating - 75) * 0.002))
    made = random.random() < probability
    return KickOutcome(made=made, yards=int(distance))


def expected_penalties_per_game(rng: Random, plays: int = 130, rate: float = 0.07) -> int:
    return sum(1 for _ in range(plays) if rng.random() < rate)

