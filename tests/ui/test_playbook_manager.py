import json
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
except ModuleNotFoundError:  # pragma: no cover - test environment guard
    pytest.skip("PyQt6 not available", allow_module_level=True)

from domain.teams import TeamInfo
from ui.core import EventBus
from ui.playbooks import PlaybookManagerPage


def _write_play(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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
        self._team = TeamInfo(team_id="TST", name="Testers", city="Test", abbreviation="TST")

    @property
    def selected_team(self) -> TeamInfo:
        return self._team


def _offense_play() -> dict:
    return {
        "play_id": "mesh_right",
        "name": "Mesh Right",
        "formation": "Gun Trips",
        "personnel": "11",
        "play_type": "offense",
        "assignments": [
            {"player_id": "QB1", "role": "pass", "route": None},
            {
                "player_id": "WR1",
                "role": "route",
                "route": [
                    {"timestamp": 0.0, "x": -6.0, "y": 0.0},
                    {"timestamp": 1.0, "x": 0.0, "y": 8.0},
                ],
            },
            {"player_id": "RB1", "role": "carry", "route": None},
        ],
    }


def _defense_play() -> dict:
    return {
        "play_id": "robber",
        "name": "Robber",
        "formation": "Nickel",
        "personnel": "Nickel",
        "play_type": "defense",
        "assignments": [
            {
                "player_id": "CB1",
                "role": "defend",
                "route": [
                    {"timestamp": 0.0, "x": -10.0, "y": 0.0},
                    {"timestamp": 1.0, "x": -8.0, "y": 15.0},
                ],
            },
            {
                "player_id": "LB1",
                "role": "rush",
                "route": [
                    {"timestamp": 0.0, "x": 0.0, "y": 0.0},
                    {"timestamp": 0.9, "x": 0.0, "y": 8.5},
                ],
            },
        ],
    }


@pytest.mark.usefixtures("qt_app")
def test_playbook_manager_loads_and_emits(tmp_path: Path) -> None:
    plays_dir = tmp_path / "plays"
    plays_dir.mkdir()
    _write_play(plays_dir / "mesh_right.json", _offense_play())
    _write_play(plays_dir / "robber.json", _defense_play())

    bus = EventBus()
    team_store = DummyTeamStore()
    page = PlaybookManagerPage(team_store, bus, user_home=tmp_path / "home", plays_dir=plays_dir)

    offense_rows = page._offense_tab._table_model.rowCount()
    defense_rows = page._defense_tab._table_model.rowCount()
    assert offense_rows == 1
    assert defense_rows == 1

    captured: list[dict] = []
    bus.subscribe("gameplan.play.attached", lambda payload: captured.append(payload))
    page._offense_tab._assign_button.click()

    assert captured
    event = captured[0]
    assert event["play_id"] == "mesh_right"
    assert event["team_id"] == "TST"
