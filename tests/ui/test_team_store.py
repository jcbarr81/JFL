import os
from pathlib import Path

import pytest

from ui.core import EventBus
from ui.team.store import TeamInfo, TeamSettingsBackend, TeamStore


class _MemorySettingsBackend(TeamSettingsBackend):
    def __init__(self) -> None:
        self.value: str | None = None

    def get(self, key: str) -> str | None:
        return self.value

    def set(self, key: str, value: str) -> bool:
        self.value = value
        return True


class _StubRepository:
    def __init__(self) -> None:
        self._teams = [
            TeamInfo(team_id="ATX", name="Armadillos", city="Austin", abbreviation="ATX"),
            TeamInfo(team_id="BOS", name="Brigade", city="Boston", abbreviation="BOS"),
        ]

    def list_teams(self):
        return list(self._teams)

    def find_team(self, team_id: str, fallbacks: bool = True):
        for team in self._teams:
            if team.team_id == team_id:
                return team
        return None


@pytest.fixture(scope="session")
def qt_app():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_team_store_loads_and_emits(qt_app, tmp_path: Path) -> None:
    repo = _StubRepository()
    settings = _MemorySettingsBackend()
    bus = EventBus()
    store = TeamStore(tmp_path, bus, repository=repo, settings_backend=settings)

    team_events: list[TeamInfo | None] = []
    store.teamChanged.connect(lambda team: team_events.append(team))

    store.load()

    assert store.selected_team is not None
    assert store.selected_team.team_id == "ATX"
    assert settings.value == "ATX"
    assert isinstance(team_events[-1], TeamInfo)

    bus_events: list[TeamInfo] = []
    bus.subscribe("team.changed", lambda payload: bus_events.append(payload))

    store.set_selected_team("BOS")

    assert store.selected_team is not None and store.selected_team.team_id == "BOS"
    assert settings.value == "BOS"
    assert bus_events and bus_events[-1].team_id == "BOS"
