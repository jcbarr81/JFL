from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Optional

from domain.models import Attributes


@dataclass
class FatigueState:
    value: float = 0.0

    def apply(self, load: float, *, recovery: float = 0.05) -> None:
        self.value = max(0.0, min(1.0, self.value + load - recovery))

    def multiplier(self) -> float:
        return 1.0 - 0.35 * self.value


@dataclass
class InjuryOutcome:
    injured: bool
    severity: Optional[str] = None


def check_injury(
    rng: Random,
    impact: float,
    attributes: Attributes,
    *,
    base_rate: float = 0.015,
) -> InjuryOutcome:
    toughness = (attributes.strength + attributes.tackling) / 200.0
    adjusted = max(0.0, base_rate + impact - toughness * 0.01)
    injured = rng.random() < adjusted
    if not injured:
        return InjuryOutcome(False, None)
    severity_roll = rng.random()
    if severity_roll < 0.7:
        severity = "minor"
    elif severity_roll < 0.93:
        severity = "moderate"
    else:
        severity = "severe"
    return InjuryOutcome(True, severity)
