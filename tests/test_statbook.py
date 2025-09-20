import pytest

from domain.models import Play
from sim.engine import simulate_play
from sim.statbook import PlayEvent, StatBook

from tests.test_engine import _load_sample_defense, _load_sample_offense


def test_statbook_reduces_pass_play() -> None:
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
                {"player_id": "WR2", "role": "route", "route": None},
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

    result = simulate_play(play, offense, defense, seed=321)

    book = StatBook()
    book.extend(result.events)

    box = book.boxscore()
    qb_stats = box["players"]["QB1"]
    assert qb_stats["pass_attempts"] == 1
    assert qb_stats["pass_completions"] == 1
    assert qb_stats["pass_yards"] >= result.yards_gained - 1e-6

    team_stats = box["teams"]["offense"]
    assert team_stats["plays"] == 1
    assert team_stats["yards"] == pytest.approx(result.yards_gained)

    rates = book.advanced_rates()
    assert rates["passers"]["QB1"]["completion_pct"] == pytest.approx(1.0)


def test_statbook_counts_sack_and_turnover() -> None:
    book = StatBook()
    book.extend(
        [
            PlayEvent(type="pass_attempt", timestamp=0.0, team="offense", player_id="QB1"),
            PlayEvent(
                type="sack",
                timestamp=0.5,
                team="defense",
                player_id="DEF1",
                target_id="QB1",
                yards=-5.0,
                metadata={"qb_id": "QB1", "yards_lost": -5.0},
            ),
            PlayEvent(
                type="play_end",
                timestamp=0.5,
                team="offense",
                player_id="QB1",
                yards=-5.0,
                metadata={
                    "play_type": "pass",
                    "passer_id": "QB1",
                    "runner_id": "QB1",
                    "receiver_id": None,
                    "air_yards": 0.0,
                    "yac": 0.0,
                    "success": False,
                    "interception": False,
                    "sack": True,
                    "completed": False,
                },
            ),
        ]
    )

    box = book.boxscore()
    assert box["players"]["QB1"]["pass_attempts"] == 1
    assert box["players"]["QB1"]["sacks_taken"] == 1
    assert box["players"]["DEF1"]["sacks"] == 1
    assert box["teams"]["offense"]["yards"] == -5.0


def test_statbook_pressure_and_interception_rates() -> None:
    book = StatBook()
    book.extend(
        [
            PlayEvent(type="pass_attempt", timestamp=0.0, team="offense", player_id="QB1"),
            PlayEvent(
                type="pressure",
                timestamp=0.2,
                team="defense",
                player_id="DEF1",
                metadata={"passer_id": "QB1", "defender_id": "DEF1"},
            ),
            PlayEvent(
                type="interception",
                timestamp=0.4,
                team="defense",
                player_id="DEF2",
                metadata={"passer_id": "QB1", "defender_id": "DEF2"},
            ),
            PlayEvent(
                type="play_end",
                timestamp=0.4,
                team="offense",
                player_id=None,
                yards=0.0,
                metadata={
                    "play_type": "pass",
                    "passer_id": "QB1",
                    "runner_id": None,
                    "receiver_id": None,
                    "air_yards": 0.0,
                    "yac": 0.0,
                    "success": False,
                    "interception": True,
                    "sack": False,
                    "completed": False,
                },
            ),
        ]
    )

    box = book.boxscore()
    assert box["players"]["QB1"]["interceptions_thrown"] == 1
    assert box["players"]["DEF2"]["interceptions_made"] == 1

    rates = book.advanced_rates()
    assert rates["passers"]["QB1"]["pressure_rate"] == pytest.approx(1.0)
    assert rates["teams"]["offense"]["success_rate"] == 0.0
