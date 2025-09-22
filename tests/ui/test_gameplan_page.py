import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6.QtWidgets import QApplication
except ModuleNotFoundError:  # pragma: no cover - CI guard
    pytest.skip("PyQt6 not available", allow_module_level=True)

from domain.teams import TeamInfo
from domain.gameplan import GameplanRepository
from ui.core import EventBus
from ui.coach import WeeklyGameplanPage


class DummyTeamRepository:
    def __init__(self) -> None:
        self._teams = [
            TeamInfo(team_id="TST", name="Testers", city="Test City", abbreviation="TST"),
            TeamInfo(team_id="OPP", name="Opponents", city="Opp City", abbreviation="OPP"),
        ]

    def list_teams(self) -> list[TeamInfo]:
        return list(self._teams)

    def find_team(self, team_id: str, *, fallbacks: bool = True) -> TeamInfo | None:  # noqa: ARG002
        for team in self._teams:
            if team.team_id == team_id:
                return team
        return None


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class DummyTeamStore(QObject):
    teamChanged = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._team = TeamInfo(team_id="TST", name="Testers", city="Test City", abbreviation="TST")

    @property
    def selected_team(self) -> TeamInfo:
        return self._team


@pytest.mark.usefixtures("qt_app")
def test_weekly_gameplan_page_loads_and_saves(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = GameplanRepository(home, team_repository=DummyTeamRepository())
    bus = EventBus()
    team_store = DummyTeamStore()

    page = WeeklyGameplanPage(team_store, bus, home, repository=repo)

    assert page._current_plan is not None
    assert "Week" in page._subtitle.text()

    captured: list[dict] = []
    bus.subscribe("gameplan.updated", lambda payload: captured.append(payload))

    page._run_slider.slider.setValue(68)
    page._handle_save()

    assert captured
    payload = captured[-1]
    assert payload["tendencies"]["run_rate"] == 68

    saved = repo.load_plan("TST", week=1)
    assert saved.tendencies.run_rate == 68

    page._handle_simulate()
    assert "Run" in page._preview_summary.text()
