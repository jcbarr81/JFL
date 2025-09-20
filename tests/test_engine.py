import random
from typing import Dict

import pytest

from domain.models import Assignment, Attributes, Play, Player, RoutePoint
from sim.engine import PlayResult, simulate_play


def _player(
    player_id: str,
    position: str,
    *,
    speed: int = 90,
    strength: int = 85,
    agility: int = 88,
    awareness: int = 88,
    catching: int = 88,
    tackling: int = 88,
    throwing_power: int = 88,
    accuracy: int = 88,
) -> Player:
    attrs = Attributes(
        speed=speed,
        strength=strength,
        agility=agility,
        awareness=awareness,
        catching=catching,
        tackling=tackling,
        throwing_power=throwing_power,
        accuracy=accuracy,
    )
    return Player(
        player_id=player_id,
        name=player_id,
        position=position,
        jersey_number=12,
        attributes=attrs,
    )


def _load_sample_offense() -> Dict[str, Player]:
    roster = {}
    roster["QB1"] = _player("QB1", "QB", accuracy=95, throwing_power=92, awareness=94)
    roster["WR1"] = _player("WR1", "WR", speed=96, catching=94, agility=95)
    roster["WR2"] = _player("WR2", "WR", speed=92, catching=88, agility=90)
    roster["RB1"] = _player("RB1", "RB", speed=90, agility=90, catching=70)
    roster["LT"] = _player("LT", "OL", strength=95, tackling=80)
    roster["LG"] = _player("LG", "OL", strength=95, tackling=80)
    roster["C"] = _player("C", "OL", strength=95, tackling=80)
    roster["RG"] = _player("RG", "OL", strength=95, tackling=80)
    roster["RT"] = _player("RT", "OL", strength=95, tackling=80)
    return roster


def _load_sample_defense(count: int = 11) -> Dict[str, Player]:
    roster: Dict[str, Player] = {}
    for index in range(count):
        identifier = f"DEF{index}"
        roster[identifier] = _player(
            identifier,
            position="CB" if index < 4 else "LB",
            speed=88,
            agility=85,
            awareness=82,
            tackling=90,
            catching=50,
        )
    return roster


def test_simulate_pass_play_completes_with_high_accuracy() -> None:
    play = Play.model_validate(
        {
            "play_id": "quick_slant_right",
            "name": "Quick Slant Right",
            "formation": "Shotgun Trips Right",
            "personnel": "11",
            "play_type": "offense",
            "assignments": [
                {"player_id": "QB1", "role": "pass", "route": None},
                {
                    "player_id": "WR1",
                    "role": "route",
                    "route": [
                        {"timestamp": 0.0, "x": -5.0, "y": 0.0},
                        {"timestamp": 1.1, "x": -2.0, "y": 8.0},
                    ],
                },
                {
                    "player_id": "WR2",
                    "role": "route",
                    "route": [
                        {"timestamp": 0.0, "x": 5.0, "y": 0.0},
                        {"timestamp": 1.3, "x": 8.0, "y": 6.0},
                    ],
                },
                {"player_id": "RB1", "role": "carry", "route": None},
                {"player_id": "LT", "role": "block", "route": None},
                {"player_id": "LG", "role": "block", "route": None},
                {"player_id": "C", "role": "block", "route": None},
                {"player_id": "RG", "role": "block", "route": None},
                {"player_id": "RT", "role": "block", "route": None},
            ],
        }
    )

    offense = _load_sample_offense()
    defense = _load_sample_defense()

    result = simulate_play(play, offense, defense, seed=1234)

    assert result.play_type == "pass"
    assert result.completed is True
    assert result.sack is False
    assert result.yards_gained > 0
    assert result.yards_gained + 1e-6 >= result.air_yards - 0.5

    event_types = [event.type for event in result.events]
    assert "snap" in event_types
    assert "pass_attempt" in event_types
    assert "pass_completion" in event_types
    assert event_types.count("play_end") == 1


def test_simulate_run_play_advances_yards() -> None:
    play = Play(
        play_id="inside_zone",
        name="Inside Zone",
        formation="Singleback",
        personnel="12",
        play_type="offense",
        assignments=[
            {"player_id": "RB1", "role": "carry", "route": [
                RoutePoint(timestamp=0.0, x=0.0, y=0.0),
                RoutePoint(timestamp=2.0, x=0.0, y=8.0),
            ]},
            Assignment(player_id="LT", role="block", route=None),
            Assignment(player_id="LG", role="block", route=None),
            Assignment(player_id="C", role="block", route=None),
            Assignment(player_id="RG", role="block", route=None),
            Assignment(player_id="RT", role="block", route=None),
        ],
    )

    offense = _load_sample_offense()
    defense = _load_sample_defense()

    result = simulate_play(play, offense, defense, seed=2025)

    assert result.play_type == "run"
    assert result.yards_gained >= 0
    assert result.sack is False
    assert result.interception is False

    event_types = [event.type for event in result.events]
    assert "rush_attempt" in event_types
    assert event_types.count("play_end") == 1


def test_simulation_is_deterministic_for_same_seed() -> None:
    play = Play(
        play_id="qb_draw",
        name="QB Draw",
        formation="Shotgun",
        personnel="10",
        play_type="offense",
        assignments=[
            Assignment(player_id="QB1", role="carry", route=[
                RoutePoint(timestamp=0.0, x=0.0, y=0.0),
                RoutePoint(timestamp=1.5, x=0.0, y=7.0),
            ]),
            Assignment(player_id="LT", role="block", route=None),
            Assignment(player_id="LG", role="block", route=None),
            Assignment(player_id="C", role="block", route=None),
            Assignment(player_id="RG", role="block", route=None),
            Assignment(player_id="RT", role="block", route=None),
        ],
    )

    offense = _load_sample_offense()
    defense = _load_sample_defense()

    result_one = simulate_play(play, offense, defense, seed=999)
    result_two = simulate_play(play, offense, defense, seed=999)

    assert result_one == result_two

    result_three = simulate_play(play, offense, defense, seed=1000)
    assert result_three != result_one
