from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Sequence

from PyQt6.QtCore import QObject, pyqtSignal

from ui.core import EventBus
from domain import settings as settings_repo
from domain.teams import TeamInfo, TeamRepository

LOGGER = logging.getLogger("ui.team.store")

_SETTINGS_KEY = "ui.selected_team"


class TeamSettingsBackend:
    """Abstract persistence backend for team preferences."""

    def get(self, key: str) -> Optional[str]:  # pragma: no cover - interface
        raise NotImplementedError

    def set(self, key: str, value: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class DatabaseSettingsBackend(TeamSettingsBackend):
    def get(self, key: str) -> Optional[str]:
        return settings_repo.get_setting(key)

    def set(self, key: str, value: str) -> bool:
        return settings_repo.set_setting(key, value)


class JsonFallbackSettingsBackend(TeamSettingsBackend):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[str]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
            return None
        return data.get(key)

    def set(self, key: str, value: str) -> bool:
        data = {}
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
                data = {}
        data[key] = value
        try:
            self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        except OSError:  # pragma: no cover - defensive
            return False


class CompositeSettingsBackend(TeamSettingsBackend):
    """Uses a primary backend with a JSON fallback for resilience."""

    def __init__(self, primary: TeamSettingsBackend, fallback: TeamSettingsBackend) -> None:
        self._primary = primary
        self._fallback = fallback

    def get(self, key: str) -> Optional[str]:
        value = self._primary.get(key)
        if value is not None:
            return value
        return self._fallback.get(key)

    def set(self, key: str, value: str) -> bool:
        primary_ok = self._primary.set(key, value)
        fallback_ok = self._fallback.set(key, value)
        return primary_ok or fallback_ok


class TeamStore(QObject):
    """Manages available teams and the active user selection."""

    teamChanged = pyqtSignal(object)
    teamsLoaded = pyqtSignal(object)

    def __init__(
        self,
        user_home: Path,
        event_bus: EventBus,
        *,
        repository: Optional[TeamRepository] = None,
        settings_backend: Optional[TeamSettingsBackend] = None,
    ) -> None:
        super().__init__()
        self._event_bus = event_bus
        self._repository = repository or TeamRepository()
        fallback_backend = JsonFallbackSettingsBackend(user_home / "settings" / "ui.json")
        primary_backend = settings_backend or DatabaseSettingsBackend()
        self._settings = CompositeSettingsBackend(primary_backend, fallback_backend)
        self._teams: List[TeamInfo] = []
        self._selected: TeamInfo | None = None

    def load(self) -> None:
        self._teams = self._repository.list_teams()
        self.teamsLoaded.emit(list(self._teams))
        desired_id = self._settings.get(_SETTINGS_KEY)
        selected = self._team_by_id(desired_id) if desired_id else None
        if selected is None and self._teams:
            selected = self._teams[0]
            self._persist_selection(selected.team_id)
        self._apply_selection(selected, emit=True)

    def refresh(self) -> None:
        self.load()

    def teams(self) -> Sequence[TeamInfo]:
        return tuple(self._teams)

    @property
    def selected_team(self) -> TeamInfo | None:
        return self._selected

    def set_selected_team(self, team_id: str) -> None:
        team = self._team_by_id(team_id)
        if team is None:
            LOGGER.warning("Attempted to select unknown team '%s'", team_id)
            return
        if self._selected and self._selected.team_id == team.team_id:
            return
        self._persist_selection(team.team_id)
        self._apply_selection(team, emit=True)

    def _team_by_id(self, team_id: Optional[str]) -> Optional[TeamInfo]:
        if not team_id:
            return None
        for team in self._teams:
            if team.team_id == team_id:
                return team
        lookup = self._repository.find_team(team_id)
        if lookup and all(existing.team_id != lookup.team_id for existing in self._teams):
            self._teams.append(lookup)
            self.teamsLoaded.emit(list(self._teams))
        return lookup

    def _persist_selection(self, team_id: str) -> None:
        if not self._settings.set(_SETTINGS_KEY, team_id):
            LOGGER.warning("Failed to persist selected team '%s'", team_id)

    def _apply_selection(self, team: TeamInfo | None, *, emit: bool) -> None:
        self._selected = team
        if emit:
            self.teamChanged.emit(team)
            self._event_bus.emit("team.changed", team)
