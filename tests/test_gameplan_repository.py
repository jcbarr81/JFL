from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.gameplan import GameplanRepository
from domain.teams import TeamInfo


class DummyTeamRepository:
    def __init__(self) -> None:
        self._teams = [
            TeamInfo(team_id="TST", name="Testers", city="Test City", abbreviation="TST"),
            TeamInfo(team_id="OPP", name="Opponents", city="Opp City", abbreviation="OPP"),
        ]

    def list_teams(self) -> list[TeamInfo]:
        return list(self._teams)

    def find_team(self, team_id: str, *, fallbacks: bool = True) -> TeamInfo | None:  # noqa: ARG002 - fallbacks unused
        for team in self._teams:
            if team.team_id == team_id:
                return team
        return None


def test_gameplan_repository_load_save_roundtrip(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = GameplanRepository(home, team_repository=DummyTeamRepository())

    plan = repo.load_plan("TST", week=3)
    assert plan.team_id == "TST"
    assert plan.week == 3
    assert plan.opponent_id == "OPP"
    assert plan.situations

    plan.tendencies.run_rate = 61
    plan.notes = "Attack edges"
    repo.save_plan(plan)

    reloaded = repo.load_plan("TST", week=3)
    assert reloaded.tendencies.run_rate == 61
    assert "Attack" in reloaded.notes


def test_gameplan_repository_preview_and_export(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = GameplanRepository(home, team_repository=DummyTeamRepository())
    plan = repo.load_plan("TST", week=1)

    preview = repo.preview(plan, drives=8)
    assert preview.expected_run_calls + preview.expected_pass_calls > 0
    assert 0.0 < preview.explosive_play_chance < 1.0

    export_path = tmp_path / "plan.json"
    repo.export_plan(plan, export_path)
    assert export_path.exists()

    imported = repo.import_plan(export_path, override_ids=("TST", "OPP", 4))
    assert imported.week == 4
    assert imported.opponent_id == "OPP"
    assert imported.team_id == "TST"


def test_gameplan_repository_records_execution(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = GameplanRepository(home)
    plan = repo.load_plan("TST", week=2)
    actual = {
        "run_rate": 55.0,
        "deep_shot_rate": 28.0,
        "blitz_rate": 22.0,
        "zone_rate": 63.0,
    }
    execution = repo.record_execution(plan.team_id, plan.opponent_id, plan.week, actual)
    assert execution.actual["run_rate"] == 55.0
    reloaded = repo.load_plan("TST", week=2)
    assert reloaded.last_execution is not None
    assert reloaded.last_execution.actual["zone_rate"] == 63.0
