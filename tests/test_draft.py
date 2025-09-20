from __future__ import annotations

from statistics import mean

import pytest

from domain.models import Attributes, Player
from sim.draft import Prospect, generate_draft_class, run_draft


def _collect_attributes(prospects: list[Prospect], key: str) -> list[int]:
    return [getattr(p.hidden_attributes, key) for p in prospects]


def test_generate_draft_class_size_and_bounds() -> None:
    sizes = {"QB": 10, "WR": 20, "DL": 30}
    prospects = generate_draft_class(2025, sizes, seed=42)
    assert len(prospects) == sum(sizes.values())
    for prospect in prospects:
        attrs = prospect.hidden_attributes
        for value in attrs.__dict__.values():
            assert 0 <= value <= 99

    qb_speeds = _collect_attributes([p for p in prospects if p.position == "QB"], "speed")
    assert 65 <= mean(qb_speeds) <= 85


def test_public_attributes_include_noise() -> None:
    sizes = {"WR": 5}
    prospects = generate_draft_class(2025, sizes, seed=7, noise_std=10)
    differences = [
        abs(p.hidden_attributes.speed - p.public_attributes.speed) for p in prospects
    ]
    assert any(diff > 0 for diff in differences)


def test_run_draft_distributes_prospects() -> None:
    teams = {"A": [], "B": [], "C": []}
    prospects = generate_draft_class(2025, {"RB": 9}, seed=99)
    updated = run_draft(teams, prospects, seed=3)
    total_players = sum(len(roster) for roster in updated.values())
    assert total_players == len(prospects)

