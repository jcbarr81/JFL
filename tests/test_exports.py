from __future__ import annotations

import json
from pathlib import Path

from domain.models import Attributes, Player
from sim.exports import export_injuries, export_player_stats, export_standings, export_team_stats
from sim.schedule import SeasonResult
from sim.statbook import PlayEvent, StatBook


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


def _season_result() -> SeasonResult:
    teams = {
        "HOME": {
            "HOME_QB": _player("HOME_QB", "QB"),
            "HOME_WR": _player("HOME_WR", "WR"),
        },
        "AWAY": {
            "AWAY_QB": _player("AWAY_QB", "QB"),
            "AWAY_WR": _player("AWAY_WR", "WR"),
        },
    }
    home_book = StatBook()
    away_book = StatBook()
    home_book.extend(
        [
            PlayEvent(
                type="play_end",
                timestamp=1.0,
                team="offense",
                player_id="HOME_QB",
                yards=12.0,
                metadata={"play_type": "pass", "passer_id": "HOME_QB", "receiver_id": "HOME_WR"},
            ),
            PlayEvent(
                type="injury",
                timestamp=2.0,
                team="offense",
                player_id="HOME_WR",
                metadata={"severity": "moderate"},
            ),
        ]
    )
    away_book.extend(
        [
            PlayEvent(
                type="play_end",
                timestamp=1.5,
                team="offense",
                player_id="AWAY_QB",
                yards=7.0,
                metadata={"play_type": "pass", "passer_id": "AWAY_QB", "receiver_id": "AWAY_WR"},
            ),
        ]
    )
    standings = [("HOME", 1, 0), ("AWAY", 0, 1)]
    game_results = []
    team_books = {"HOME": home_book, "AWAY": away_book}
    return SeasonResult(standings=standings, game_results=game_results, team_books=team_books)


def test_export_outputs(tmp_path: Path) -> None:
    result = _season_result()
    export_standings(result, tmp_path / "standings.csv")
    export_team_stats(result, tmp_path / "team_stats.csv")
    export_player_stats(result, tmp_path / "player_stats.csv")
    export_injuries(result, tmp_path / "injuries.json")

    standings = (tmp_path / "standings.csv").read_text(encoding="utf-8").strip().splitlines()
    assert standings[0] == "team_id,wins,losses"
    assert "HOME" in standings[1]

    injuries = json.loads((tmp_path / "injuries.json").read_text(encoding="utf-8"))
    assert injuries and injuries[0]["player_id"] == "HOME_WR"
