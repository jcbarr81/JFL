from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from domain.scouting import ScoutingRepository
from domain.teams import TeamInfo


def test_budget_controls_noise(tmp_path: Path) -> None:
    repo = ScoutingRepository(tmp_path)
    first = repo.list_prospects()[0]
    profile = repo.get_prospect(first.prospect_id)
    assert profile is not None

    repo.set_budget(15)
    noisy = next(report for report in repo.list_prospects() if report.prospect_id == first.prospect_id)
    repo.set_budget(90)
    precise = next(report for report in repo.list_prospects() if report.prospect_id == first.prospect_id)

    assert abs(precise.grade - profile.true_grade) <= abs(noisy.grade - profile.true_grade)


def test_watchlist_and_board(tmp_path: Path) -> None:
    repo = ScoutingRepository(tmp_path)
    prospect_id = repo.list_prospects()[0].prospect_id
    repo.set_watchlist(prospect_id, True)
    assert repo.list_prospects(watchlist_only=True)[0].prospect_id == prospect_id

    repo.assign_to_tier(prospect_id, "T1")
    board = repo.get_board()
    assert board["T1"] == [prospect_id]

    repo.remove_from_board(prospect_id)
    board = repo.get_board()
    assert prospect_id not in board["T1"]


def test_record_draft_pick_updates_roster(tmp_path: Path) -> None:
    user_home = tmp_path / "user"
    settings = user_home / "settings"
    settings.mkdir(parents=True, exist_ok=True)

    rosters_path = settings / "rosters.json"
    rosters_path.write_text(
        json.dumps(
            {
                "NYG": [
                    {
                        "player_id": "nyg_qb1",
                        "name": "Giants QB",
                        "position": "QB",
                        "jersey_number": 10,
                        "overall": 86,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repo = ScoutingRepository(user_home)
    prospect = repo.list_prospects()[0]
    team = TeamInfo(team_id="NYG", name="Giants", city="New York", abbreviation="NYG")

    result = repo.record_draft_pick(team, prospect.prospect_id, 1, 5)
    assert result is not None
    roster_players = repo._roster_repo.list_players("NYG")  # type: ignore[attr-defined]
    assert any(player.player_id == result.roster_player.player_id for player in roster_players)
    recap = repo.list_draft_recap()
    assert recap and recap[0].prospect_id == prospect.prospect_id

def test_export_files(tmp_path: Path) -> None:
    repo = ScoutingRepository(tmp_path)
    class_path = repo.export_draft_class()
    results_path = repo.export_draft_results()
    assert class_path.exists()
    assert results_path.exists()
    assert class_path.read_text(encoding="utf-8").startswith("Prospect ID")
    # results may be empty early season but header should exist
    assert results_path.read_text(encoding="utf-8").startswith("Pick")
