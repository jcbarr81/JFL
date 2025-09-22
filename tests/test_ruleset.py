from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.gameplan import GameplanTendencies, WeeklyGameplan

from random import Random

from domain.models import Attributes, Player
from sim.ai_decision import PlayChoice
from sim.engine import PlayResult
from sim.fatigue import InjuryOutcome
from sim.ruleset import (
    GameConfig,
    PenaltyDecision,
    _TeamState,
    _handle_special_down,
    _maybe_apply_penalty,
    simulate_game,
)
from sim.special_teams import KickOutcome, PenaltyType
from sim.statbook import PlayEvent, StatBook


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

def _weekly_plan(code: str, opponent: str, week: int, *, run: int = 60, deep: int = 32, blitz: int = 25, zone: int = 60) -> WeeklyGameplan:
    return WeeklyGameplan(
        team_id=code,
        opponent_id=opponent,
        week=week,
        tendencies=GameplanTendencies(
            run_rate=run,
            deep_shot_rate=deep,
            blitz_rate=blitz,
            zone_rate=zone,
        ),
        situations=[],
        notes="Test plan",
    )



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





def test_simulate_game_tracks_gameplan_usage() -> None:
    home_roster = _build_roster("HOME")
    away_roster = _build_roster("AWAY")
    home_plan = _weekly_plan("Home Club", "Away Club", 1, run=78, deep=18, blitz=12, zone=82)
    away_plan = _weekly_plan("Away Club", "Home Club", 1, run=45, deep=48, blitz=34, zone=48)
    summary = simulate_game(
        "Home Club",
        home_roster,
        StatBook(),
        "Away Club",
        away_roster,
        StatBook(),
        seed=2024,
        config=GameConfig(quarter_length=240.0, quarters=2, max_plays=70),
        home_plan=home_plan,
        away_plan=away_plan,
    )

    home_result = summary.gameplan_results.get("Home Club")
    assert home_result is not None
    assert home_result["plan"]["run_rate"] == 78
    actual = home_result["actual"]
    away_actual = summary.gameplan_results["Away Club"]["actual"]
    assert actual["zone_rate"] >= away_actual["zone_rate"]
    assert actual["blitz_rate"] <= away_actual["blitz_rate"]
    comparison = home_result["comparison"]
    assert "summary" in comparison
    assert isinstance(comparison["summary"], str)
    assert isinstance(comparison["summary"], str)

def test_handle_special_down_field_goal_success(monkeypatch) -> None:
    home_roster = _build_roster("HOME")
    home_roster["HOME_K"] = _player("HOME_K", "K")
    away_roster = _build_roster("AWAY")
    offense_state = _TeamState("HOME", home_roster, StatBook())
    defense_state = _TeamState("AWAY", away_roster, StatBook())

    monkeypatch.setattr(
        "sim.ruleset.attempt_field_goal",
        lambda yardline, rating, rng: KickOutcome(True, 45),
    )

    outcome = _handle_special_down(offense_state, defense_state, 70.0, Random(0), drive_index=1)

    assert outcome.result == "FG"
    assert outcome.points == 3
    assert any(evt.type == "field_goal_attempt" for evt in outcome.events)
    assert offense_state.fatigue_state("HOME_K").value > 0


def test_handle_special_down_punt_changes_possession() -> None:
    home_roster = _build_roster("HOME")
    home_roster["HOME_P"] = _player("HOME_P", "P")
    away_roster = _build_roster("AWAY")
    offense_state = _TeamState("HOME", home_roster, StatBook())
    defense_state = _TeamState("AWAY", away_roster, StatBook())

    outcome = _handle_special_down(offense_state, defense_state, 40.0, Random(0), drive_index=1)

    assert outcome.result == "PUNT"
    assert outcome.change_possession is True
    assert 1.0 <= outcome.next_start <= 50.0
    assert any(evt.type == "punt" for evt in outcome.events)


def test_penalty_enforcement_repeat_down(monkeypatch) -> None:
    offense_state = _TeamState("HOME", _build_roster("HOME"), StatBook())
    defense_state = _TeamState("AWAY", _build_roster("AWAY"), StatBook())

    result = PlayResult(
        play_type="pass",
        yards_gained=12.0,
        air_yards=10.0,
        yac=2.0,
        duration=4.0,
        pressure=False,
        sack=False,
        interception=False,
        completed=True,
        events=[
            PlayEvent(
                type="play_end",
                timestamp=4.0,
                team="offense",
                yards=12.0,
                metadata={"play_type": "pass"},
            )
        ],
    )

    monkeypatch.setattr(
        "sim.ruleset._draw_penalty",
        lambda result, rng: PenaltyDecision(team="offense", penalty=PenaltyType.HOLDING),
    )

    resolution = _maybe_apply_penalty(
        offense_state,
        defense_state,
        result,
        pre_yardline=50.0,
        yardline=62.0,
        pre_down=2,
        down=2,
        pre_yards_to_first=8.0,
        yards_to_first=0.0,
        rng=Random(0),
    )

    assert resolution.applied is True
    assert resolution.repeat_down is True
    assert resolution.force_first_down is False
    assert resolution.yardline < 50.0
    assert result.events[-1].type == "penalty"


def test_injury_event_triggers_substitution(monkeypatch) -> None:
    def _player(pid: str, pos: str) -> Player:
        attrs = Attributes(
            speed=82,
            strength=78,
            agility=80,
            awareness=75,
            catching=68,
            tackling=70,
            throwing_power=65,
            accuracy=65,
        )
        return Player(player_id=pid, name=pid, position=pos, jersey_number=10, attributes=attrs)

    def _roster(prefix: str) -> dict[str, Player]:
        positions = [
            "QB",
            "RB",
            "RB",
            "WR",
            "WR",
            "WR",
            "TE",
            "OL",
            "OL",
            "OL",
            "OL",
            "OL",
            "DL",
            "DL",
            "DL",
            "LB",
            "LB",
            "CB",
            "CB",
            "S",
            "S",
        ]
        return {f"{prefix}_{index}": _player(f"{prefix}_{index}", pos) for index, pos in enumerate(positions, start=1)}

    home_roster = _roster("HOME")
    away_roster = _roster("AWAY")

    home_book = StatBook()
    away_book = StatBook()

    def fake_call_offense(context, rng, plan_bias=None):
        return PlayChoice("run")

    injury_calls = {"count": 0}

    def fake_check_injury(rng, impact, attributes, *, base_rate=0.015):
        injury_calls["count"] += 1
        if injury_calls["count"] == 1:
            return InjuryOutcome(True, "moderate")
        return InjuryOutcome(False, None)

    monkeypatch.setattr("sim.ruleset.call_offense", fake_call_offense)
    monkeypatch.setattr("sim.ruleset.check_injury", fake_check_injury)
    monkeypatch.setattr("sim.ruleset.Random.choice", lambda self, seq: seq[0])
    monkeypatch.setattr("sim.ruleset._draw_penalty", lambda result, rng: None)

    config = GameConfig(quarter_length=120.0, quarters=1, max_plays=6)
    simulate_game(
        "HOME",
        home_roster,
        home_book,
        "AWAY",
        away_roster,
        away_book,
        seed=5,
        config=config,
    )

    injury_events = [evt for evt in home_book.events if evt.type == "injury"]
    assert injury_events
    assert injury_events[0].player_id == "HOME_2"

    runners = [
        (evt.metadata or {}).get("runner_id")
        for evt in home_book.events
        if evt.type == "play_end" and (evt.metadata or {}).get("play_type") == "run"
    ]
    assert "HOME_3" in runners






