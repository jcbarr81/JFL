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

from .contract_page import ContractsManagementPage
from .trade_center_page import TradeCenterPage
from .scouting_page import ScoutingDraftPage


class GMHubPage(QWidget):
    """Single entry point for GM workflows in the GM navigation."""

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

        title = QLabel("GM Operations")
        title.setObjectName("coach-roster-title")
        layout.addWidget(title)

        self._subtitle = QLabel("Manage contracts and cap space.")
        self._subtitle.setObjectName("section-subtitle")
        layout.addWidget(self._subtitle)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(8)
        layout.addLayout(nav_row)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        self._contracts_button = SecondaryButton("Contracts & Cap", self)
        self._contracts_button.setCheckable(True)
        nav_row.addWidget(self._contracts_button)
        self._nav_group.addButton(self._contracts_button, 0)

        self._trades_button = SecondaryButton("Trade Center", self)
        self._trades_button.setCheckable(True)
        nav_row.addWidget(self._trades_button)
        self._nav_group.addButton(self._trades_button, 1)

        self._scouting_button = SecondaryButton("Scouting & Draft", self)
        self._scouting_button.setCheckable(True)
        nav_row.addWidget(self._scouting_button)
        self._nav_group.addButton(self._scouting_button, 2)

        nav_row.addStretch(1)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)

        self._contracts_page = ContractsManagementPage(
            team_store,
            event_bus,
            user_home,
            parent=self,
        )
        self._trade_page = TradeCenterPage(
            team_store,
            event_bus,
            user_home,
            parent=self,
        )
        self._scouting_page = ScoutingDraftPage(
            team_store,
            event_bus,
            user_home,
            parent=self,
        )

        self._stack.addWidget(self._contracts_page)
        self._stack.addWidget(self._trade_page)
        self._stack.addWidget(self._scouting_page)

        self._nav_group.idClicked.connect(self._on_tab_changed)  # type: ignore[arg-type]
        self._contracts_button.setChecked(True)
        self._stack.setCurrentIndex(0)

    def _on_tab_changed(self, tab_id: int) -> None:
        if tab_id not in (0, 1, 2):
            return
        self._stack.setCurrentIndex(tab_id)
        if tab_id == 0:
            self._subtitle.setText("Manage contracts and cap space.")
        elif tab_id == 1:
            self._subtitle.setText("Build trade offers, compare value, and undo moves.")
            self._trade_page.refresh()
        elif tab_id == 2:
            self._subtitle.setText("Scout prospects, build your board, and log draft picks.")
            self._scouting_page.refresh()

    def shutdown(self) -> None:
        self._contracts_page.shutdown()
        self._trade_page.shutdown()
        self._scouting_page.shutdown()
