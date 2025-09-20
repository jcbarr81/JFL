from __future__ import annotations

from random import Random
from statistics import mean

import pytest

from sim.special_teams import (
    PenaltyType,
    apply_penalty,
    attempt_field_goal,
    expected_penalties_per_game,
)


def test_apply_penalty_acceptance_and_yards() -> None:
    result = apply_penalty(PenaltyType.HOLDING)
    assert result.accepted is True
    assert result.yards == 10
    assert result.automatic_first is False

    dpi = apply_penalty(PenaltyType.DPI)
    assert dpi.yards == 15
    assert dpi.automatic_first is True

    declined = apply_penalty(PenaltyType.OFFSIDES, accept=False)
    assert declined.accepted is False
    assert declined.yards == 0


def test_field_goal_probabilities_reasonable() -> None:
    rng = Random(123)
    attempts = 5000
    short = [attempt_field_goal(82, 80, rng).made for _ in range(attempts)]
    medium = [attempt_field_goal(70, 80, rng).made for _ in range(attempts)]
    long = [attempt_field_goal(60, 80, rng).made for _ in range(attempts)]
    assert 0.85 <= mean(short) <= 0.95
    assert 0.7 <= mean(medium) <= 0.85
    assert 0.45 <= mean(long) <= 0.7


def test_expected_penalties_rate() -> None:
    rng = Random(42)
    penalties = [expected_penalties_per_game(rng) for _ in range(200)]
    assert 4 <= mean(penalties) <= 9
