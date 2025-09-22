from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.core import (
    Card,
    DataTable,
    EventBus,
    PrimaryButton,
    SecondaryButton,
    StatePlaceholder,
)
from domain.teams import TeamProfileData, TeamRepository
from .store import TeamInfo, TeamStore


class TeamProfilePage(QWidget):
    """Displays high-level information about the active franchise."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        repository: Optional[TeamRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._event_bus = event_bus
        self._team_store = team_store
        self._repository = repository or TeamRepository()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending: Future[TeamProfileData] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._placeholder = StatePlaceholder(
            "Select a team",
            "Choose a franchise to view its profile.",
            variant="empty",
            parent=self,
        )
        layout.addWidget(self._placeholder)

        self._summary_card = Card(self)
        summary_layout = QVBoxLayout(self._summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(8)
        self._team_name_label = QLabel("--", self._summary_card)
        self._team_name_label.setObjectName("team-profile-title")
        self._team_name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        summary_layout.addWidget(self._team_name_label)
        self._games_label = QLabel("Games played: --", self._summary_card)
        summary_layout.addWidget(self._games_label)
        layout.addWidget(self._summary_card)
        self._summary_card.hide()

        self._stats_card = Card(self)
        stats_layout = QVBoxLayout(self._stats_card)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(8)
        stats_layout.addWidget(QLabel("Team Performance", self._stats_card))
        self._stats_table = DataTable(self._stats_card)
        stats_layout.addWidget(self._stats_table)
        self._stats_empty_label = QLabel("No game data yet", self._stats_card)
        self._stats_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_layout.addWidget(self._stats_empty_label)
        layout.addWidget(self._stats_card)
        self._stats_card.hide()

        self._recent_card = Card(self)
        recent_layout = QVBoxLayout(self._recent_card)
        recent_layout.setContentsMargins(16, 16, 16, 16)
        recent_layout.setSpacing(8)
        recent_layout.addWidget(QLabel("Recent Games", self._recent_card))
        self._recent_container = QWidget(self._recent_card)
        self._recent_container_layout = QVBoxLayout(self._recent_container)
        self._recent_container_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_container_layout.setSpacing(4)
        recent_layout.addWidget(self._recent_container)
        self._recent_empty_label = QLabel("No recent games available", self._recent_card)
        self._recent_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_layout.addWidget(self._recent_empty_label)
        layout.addWidget(self._recent_card)
        self._recent_card.hide()

        self._links_card = Card(self)
        links_layout = QVBoxLayout(self._links_card)
        links_layout.setContentsMargins(16, 16, 16, 16)
        links_layout.setSpacing(8)
        links_layout.addWidget(QLabel("Quick Links", self._links_card))
        roster_button = PrimaryButton("Open Depth Chart", self._links_card)
        roster_button.clicked.connect(lambda: self._event_bus.emit("nav.request", "coach"))  # type: ignore[arg-type]
        links_layout.addWidget(roster_button)
        contracts_button = SecondaryButton("Manage Contracts", self._links_card)
        contracts_button.clicked.connect(lambda: self._event_bus.emit("nav.request", "gm"))  # type: ignore[arg-type]
        links_layout.addWidget(contracts_button)
        playbooks_button = SecondaryButton("Edit Playbooks", self._links_card)
        playbooks_button.clicked.connect(lambda: self._event_bus.emit("nav.request", "playbooks"))  # type: ignore[arg-type]
        links_layout.addWidget(playbooks_button)
        layout.addWidget(self._links_card)
        self._links_card.hide()

        team_store.teamChanged.connect(self._on_team_changed)
        if team_store.selected_team:
            self._on_team_changed(team_store.selected_team)

    def shutdown(self) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_team_changed(self, team: TeamInfo | None) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        if team is None:
            self._show_placeholder(
                title="Select a team",
                description="Choose a franchise to view its profile.",
                variant="empty",
            )
            return
        self._show_placeholder(
            title="Loading team profile",
            description=f"Fetching updated data for {team.display_name}.",
            variant="loading",
        )
        future = self._executor.submit(self._repository.load_profile, team.team_id)
        self._pending = future
        future.add_done_callback(self._handle_future_completed)

    def _handle_future_completed(self, future: Future[TeamProfileData]) -> None:
        if future.cancelled():
            return
        try:
            data = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            QTimer.singleShot(0, lambda: self._show_placeholder("Unable to load team profile", str(exc), "error"))
            return
        QTimer.singleShot(0, lambda: self._apply_profile(data))

    def _show_placeholder(self, title: str, description: Optional[str], variant: str) -> None:
        self._placeholder.set_title(title)
        self._placeholder.set_description(description)
        self._placeholder.set_variant(variant)
        self._placeholder.show()
        self._summary_card.hide()
        self._stats_card.hide()
        self._recent_card.hide()
        self._links_card.hide()

    def _apply_profile(self, data: TeamProfileData) -> None:
        self._team_name_label.setText(data.team.display_name)
        self._games_label.setText(f"Games played: {data.games_played}")
        self._summary_card.show()

        model = QStandardItemModel(0, 2, self)
        model.setHorizontalHeaderLabels(["Metric", "Per Game"])
        for phase, stats in sorted(data.per_game.items()):
            for metric, value in sorted(stats.items()):
                metric_name = f"{phase.title()} {metric.replace('_', ' ').title()}"
                model.appendRow(
                    [
                        QStandardItem(metric_name),
                        QStandardItem(f"{value:.2f}"),
                    ]
                )
        if model.rowCount() > 0:
            self._stats_table.setModel(model)
            self._stats_table.show()
            self._stats_empty_label.hide()
        else:
            self._stats_table.hide()
            self._stats_empty_label.show()
        self._stats_card.show()

        self._clear_layout(self._recent_container_layout)
        if data.recent_games:
            for game in data.recent_games:
                status = "Played" if game.played else "Scheduled"
                line = QLabel(f"Week {game.week}: {game.location} vs {game.opponent} ({status})", self._recent_container)
                self._recent_container_layout.addWidget(line)
            self._recent_empty_label.hide()
        else:
            self._recent_empty_label.show()
        self._recent_card.show()

        self._links_card.show()
        self._placeholder.hide()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
