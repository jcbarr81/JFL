from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QVBoxLayout,
)

from ui.core import Card, ClickableCard, Tag
from .store import TeamInfo, TeamStore


class TeamSelectDialog(QDialog):
    """Modal dialog that lets the user choose a franchise."""

    def __init__(self, store: TeamStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self.setWindowTitle("Select Team")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        header = QLabel("Pick your franchise")
        header.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        header.setWordWrap(True)
        layout.addWidget(header)

        self._grid = QGridLayout()
        self._grid.setSpacing(12)
        self._grid.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._grid)

        self._populate_cards(store.teams())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_cards(self, teams: Iterable[TeamInfo]) -> None:
        for index, team in enumerate(teams):
            card = ClickableCard(self)
            card.setProperty("component", "card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 16, 16, 16)
            card_layout.setSpacing(8)

            title = QLabel(team.display_name, card)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setWordWrap(True)
            card_layout.addWidget(title)

            tag = Tag(team.abbreviation.upper(), card)
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(tag)

            card.clicked.connect(lambda _, team_id=team.team_id: self._handle_selection(team_id))  # type: ignore[arg-type]

            row, col = divmod(index, 3)
            self._grid.addWidget(card, row, col)

    def _handle_selection(self, team_id: str) -> None:
        self._store.set_selected_team(team_id)
        self.accept()
