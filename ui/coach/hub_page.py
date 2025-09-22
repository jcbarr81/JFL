from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.core import EventBus, SecondaryButton
from ui.team.store import TeamStore

from .gameplan_page import WeeklyGameplanPage
from .roster_page import RosterManagementPage


class CoachHubPage(QWidget):
    """Single entry point for coach workflows (roster + gameplan)."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("Coach Operations", self)
        title.setObjectName("coach-roster-title")
        layout.addWidget(title)

        self._subtitle = QLabel("Manage personnel and align your weekly strategy.", self)
        self._subtitle.setObjectName("section-subtitle")
        layout.addWidget(self._subtitle)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        layout.addLayout(nav_row)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self._roster_button = SecondaryButton("Roster & Depth Chart", self)
        self._roster_button.setCheckable(True)
        nav_row.addWidget(self._roster_button)
        self._nav_group.addButton(self._roster_button, 0)

        self._gameplan_button = SecondaryButton("Weekly Gameplan", self)
        self._gameplan_button.setCheckable(True)
        nav_row.addWidget(self._gameplan_button)
        self._nav_group.addButton(self._gameplan_button, 1)

        nav_row.addStretch(1)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        self._roster_page = RosterManagementPage(
            team_store,
            event_bus,
            user_home,
            parent=self,
        )
        self._gameplan_page = WeeklyGameplanPage(
            team_store,
            event_bus,
            user_home,
            parent=self,
        )

        self._stack.addWidget(self._roster_page)
        self._stack.addWidget(self._gameplan_page)

        self._nav_group.idClicked.connect(self._on_tab_changed)  # type: ignore[arg-type]
        self._roster_button.setChecked(True)
        self._stack.setCurrentIndex(0)

    def _on_tab_changed(self, tab_id: int) -> None:
        if tab_id == 0:
            self._stack.setCurrentIndex(0)
            self._subtitle.setText("Manage personnel and align your weekly strategy.")
        elif tab_id == 1:
            self._stack.setCurrentIndex(1)
            self._subtitle.setText("Dial in tendencies and scout the opponent.")

    def shutdown(self) -> None:
        self._roster_page.shutdown()
        self._gameplan_page.shutdown()


__all__ = ["CoachHubPage"]
