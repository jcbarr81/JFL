from __future__ import annotations

from random import Random
from statistics import mean

import pytest

from domain.models import Attributes
from sim.fatigue import FatigueState, check_injury


def _attrs(strength: int = 80, tackling: int = 80) -> Attributes:
    return Attributes(
        speed=80,
        strength=strength,
        agility=75,
        awareness=70,
        catching=60,
        tackling=tackling,
        throwing_power=60,
        accuracy=60,
    )


def test_fatigue_accumulates_and_recovers() -> None:
    state = FatigueState()
    state.apply(0.2)
    assert 0 < state.value < 0.2
    state.apply(0.3)
    assert state.value > 0.35
    multiplier = state.multiplier()
    assert 0 < multiplier < 1
    for _ in range(10):
        state.apply(0.0, recovery=0.1)
    assert state.value < 0.2


def test_injury_rates() -> None:
    rng = Random(42)
    trials = 10000
    injuries = sum(
        check_injury(rng, impact=0.01, attributes=_attrs()).injured for _ in range(trials)
    )
    rate = injuries / trials
    assert 0.005 <= rate <= 0.03

    lighter_attrs = _attrs(strength=60, tackling=60)
    rng.seed(1)
    injuries_light = sum(
        check_injury(rng, impact=0.02, attributes=lighter_attrs).injured for _ in range(trials)
    )
    assert injuries_light / trials > rate
