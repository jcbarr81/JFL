from __future__ import annotations

from domain.models import Attributes, Player
from sim.ruleset import GameConfig, simulate_game
from sim.statbook import StatBook


def _player(player_id: str, position: str) -> Player:
    attrs = Attributes(
        speed=85,
        strength=80,
        agility=82,
        awareness=78,
        catching=75,
        tackling=76,
        throwing_power=70,
        accuracy=72,
    )
    return Player(
        player_id=player_id,
        name=player_id,
        position=position,
        jersey_number=12,
        attributes=attrs,
    )


def _build_roster(prefix: str) -> dict[str, Player]:
    template = [
        ("QB1", "QB"),
        ("RB1", "RB"),
        ("RB2", "RB"),
        ("WR1", "WR"),
        ("WR2", "WR"),
        ("WR3", "WR"),
        ("TE1", "TE"),
        ("TE2", "TE"),
        ("OL1", "OL"),
        ("OL2", "OL"),
        ("OL3", "OL"),
        ("OL4", "OL"),
        ("OL5", "OL"),
        ("DL1", "DL"),
        ("DL2", "DL"),
        ("LB1", "LB"),
        ("LB2", "LB"),
        ("CB1", "CB"),
        ("CB2", "CB"),
        ("S1", "S"),
        ("S2", "S"),
    ]
    roster: dict[str, Player] = {}
    for suffix, position in template:
        player_id = f"{prefix}_{suffix}"
        roster[player_id] = _player(player_id, position)
    return roster


def test_simulate_game_produces_summary() -> None:
    home_roster = _build_roster("HOME")
    away_roster = _build_roster("AWAY")
    home_book = StatBook()
    away_book = StatBook()

    summary = simulate_game(
        "Home Club",
        home_roster,
        home_book,
        "Away Club",
        away_roster,
        away_book,
        seed=42,
        config=GameConfig(quarter_length=300.0, quarters=2, max_plays=80),
    )

    assert summary.total_plays > 0
    assert len(summary.drives) > 0
    assert summary.time_remaining >= 0
    for drive in summary.drives:
        assert drive.plays > 0
        assert drive.result
    assert len(home_book.events) > 0
    assert len(away_book.events) > 0


def test_simulate_game_deterministic() -> None:
    home_roster = _build_roster("HOME")
    away_roster = _build_roster("AWAY")

    summary_one = simulate_game(
        "Home Club",
        home_roster,
        StatBook(),
        "Away Club",
        away_roster,
        StatBook(),
        seed=99,
        config=GameConfig(quarter_length=240.0, quarters=2, max_plays=60),
    )
    summary_two = simulate_game(
        "Home Club",
        _build_roster("HOME"),
        StatBook(),
        "Away Club",
        _build_roster("AWAY"),
        StatBook(),
        seed=99,
        config=GameConfig(quarter_length=240.0, quarters=2, max_plays=60),
    )

    assert summary_one == summary_two
