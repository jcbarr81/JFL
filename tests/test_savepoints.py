from __future__ import annotations

import tempfile
from pathlib import Path

from domain.savepoint import create_savepoint, load_savepoint
from sim.schedule import simulate_season
from domain.models import Attributes, Player


def _player(pid: str, pos: str) -> Player:
    attrs = Attributes(
        speed=80,
        strength=80,
        agility=80,
        awareness=80,
        catching=70,
        tackling=70,
        throwing_power=70,
        accuracy=70,
    )
    return Player(player_id=pid, name=pid, position=pos, jersey_number=10, attributes=attrs)


def _teams(count: int) -> dict[str, dict[str, Player]]:
    rosters = {}
    template = ["QB", "RB", "WR", "WR", "TE", "OL", "OL", "DL", "LB", "CB", "S"]
    for idx in range(count):
        team_id = f"TEAM{idx}"
        roster: dict[str, Player] = {}
        for pos_index, position in enumerate(template, start=1):
            player_id = f"{team_id}_{position}{pos_index}"
            roster[player_id] = _player(player_id, position)
        rosters[team_id] = roster
    return rosters


def test_savepoint_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "gridiron.db"
    db_path.write_text("initial", encoding="utf-8")
    plays_dir = tmp_path / "plays"
    plays_dir.mkdir()
    (plays_dir / "sample.json").write_text("{}", encoding="utf-8")

    save_dir = tmp_path / "savepoints"
    create_savepoint("preseason", db_path=db_path, plays_path=plays_dir, save_dir=save_dir)

    teams = _teams(4)
    baseline = [
        (g.home_team, g.away_team, g.home_score, g.away_score)
        for g in simulate_season(teams, seed=42, workers=1).game_results
    ]

    db_path.write_text("mutated", encoding="utf-8")
    load_savepoint("preseason", db_path=db_path, plays_path=plays_dir, save_dir=save_dir)

    assert db_path.read_text(encoding="utf-8") == "initial"
    assert (plays_dir / "sample.json").exists()

    rerun = [
        (g.home_team, g.away_team, g.home_score, g.away_score)
        for g in simulate_season(teams, seed=42, workers=1).game_results
    ]
    assert rerun == baseline
