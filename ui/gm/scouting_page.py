from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDrag, QMimeData, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QSlider,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from domain.scouting import DraftPickResult, ProspectReport, ScoutingRepository
from domain.teams import TeamInfo
from ui.core import Card, EventBus, PrimaryButton, SecondaryButton
from ui.team.store import TeamInfo as StoreTeamInfo, TeamStore

PROSPECT_MIME = "application/x-gridiron-prospect"

class ProspectTable(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setDragEnabled(True)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:  # type: ignore[override]
        index = self.currentIndex()
        if not index.isValid():
            return
        payload = index.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        mime = QMimeData()
        mime.setData(PROSPECT_MIME, payload.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)

class TierListWidget(QListWidget):
    def __init__(self, tier: str, drop_handler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tier = tier
        self._drop_handler = drop_handler
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        mime = QMimeData()
        mime.setData(PROSPECT_MIME, payload.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(PROSPECT_MIME):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(PROSPECT_MIME):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        data = event.mimeData().data(PROSPECT_MIME)
        if not data:
            super().dropEvent(event)
            return
        payload = bytes(data).decode("utf-8")
        index = self.indexAt(event.position().toPoint()).row()
        self._drop_handler(payload, self._tier, index)
        event.acceptProposedAction()

class ScoutingDraftPage(QWidget):
    """Combined scouting board and draft workflow for the GM hub."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        repository: Optional[ScoutingRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._repo = repository or ScoutingRepository(user_home)

        self._our_team: Optional[StoreTeamInfo] = team_store.selected_team

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Scouting & Draft Board")
        header.setObjectName("coach-roster-title")
        layout.addWidget(header)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        control_card = Card(self)
        control_layout = QHBoxLayout(control_card)
        control_layout.setContentsMargins(16, 12, 16, 12)
        control_layout.setSpacing(12)
        layout.addWidget(control_card)

        control_layout.addWidget(QLabel("Scouting Budget"))
        self._budget_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._budget_slider.setRange(10, 100)
        self._budget_slider.setSingleStep(5)
        self._budget_slider.setValue(self._repo.get_budget())
        control_layout.addWidget(self._budget_slider)

        self._budget_value = QSpinBox(self)
        self._budget_value.setRange(10, 100)
        self._budget_value.setValue(self._repo.get_budget())
        control_layout.addWidget(self._budget_value)

        self._clarity_bar = QProgressBar(self)
        self._clarity_bar.setRange(0, 100)
        self._clarity_bar.setValue(self._repo.get_budget())
        self._clarity_bar.setFormat("Clarity %p%")
        control_layout.addWidget(self._clarity_bar)

        control_layout.addStretch(1)

        filter_card = Card(self)
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(12)
        layout.addWidget(filter_card)

        filter_layout.addWidget(QLabel("Position"))
        self._position_filter = QComboBox(self)
        self._position_filter.addItem("All", None)
        for position in ("QB", "RB", "WR", "TE", "OL", "DL", "LB", "CB", "S"):
            self._position_filter.addItem(position, position)
        filter_layout.addWidget(self._position_filter)

        self._watchlist_only = QCheckBox("Watchlist only", self)
        filter_layout.addWidget(self._watchlist_only)
        filter_layout.addStretch(1)

        boards = QGridLayout()
        boards.setContentsMargins(0, 0, 0, 0)
        boards.setSpacing(16)
        layout.addLayout(boards)

        # Prospect board ------------------------------------------------
        prospects_card = Card(self)
        prospects_layout = QVBoxLayout(prospects_card)
        prospects_layout.setContentsMargins(12, 12, 12, 12)
        prospects_layout.setSpacing(8)
        prospects_layout.addWidget(QLabel("Prospect Board"))

        self._prospect_model = QStandardItemModel(0, 7, self)
        self._prospect_model.setHorizontalHeaderLabels([
            "Name",
            "Pos",
            "College",
            "Archetype",
            "Grade",
            "Round",
            "Combine",
        ])
        self._prospect_table = ProspectTable(self)
        self._prospect_table.setModel(self._prospect_model)
        self._prospect_table.doubleClicked.connect(self._handle_toggle_watchlist)  # type: ignore[arg-type]
        prospects_layout.addWidget(self._prospect_table)

        boards.addWidget(prospects_card, 0, 0)

        # Draft tiers ---------------------------------------------------
        tiers_card = Card(self)
        tiers_layout = QVBoxLayout(tiers_card)
        tiers_layout.setContentsMargins(12, 12, 12, 12)
        tiers_layout.setSpacing(8)
        tiers_layout.addWidget(QLabel("Draft Board Tiers"))

        self._tier_rows: Dict[str, TierListWidget] = {}
        row = QHBoxLayout()
        row.setSpacing(12)
        tiers_layout.addLayout(row)
        for tier in ("T1", "T2", "T3", "T4", "T5"):
            column = QVBoxLayout()
            column.setSpacing(6)
            label = QLabel(tier)
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            column.addWidget(label)
            widget = TierListWidget(tier, self._handle_tier_drop, self)
            widget.doubleClicked.connect(self._handle_remove_from_board)  # type: ignore[arg-type]
            self._tier_rows[tier] = widget
            column.addWidget(widget)
            row.addLayout(column)
        boards.addWidget(tiers_card, 0, 1)

        # Draft day controls -------------------------------------------
        draft_card = Card(self)
        draft_layout = QVBoxLayout(draft_card)
        draft_layout.setContentsMargins(12, 12, 12, 12)
        draft_layout.setSpacing(8)
        draft_layout.addWidget(QLabel("Draft Day"))

        pick_row = QHBoxLayout()
        pick_row.setSpacing(12)
        draft_layout.addLayout(pick_row)

        pick_row.addWidget(QLabel("Round"))
        self._round_spin = QSpinBox(self)
        self._round_spin.setRange(1, 7)
        pick_row.addWidget(self._round_spin)

        pick_row.addWidget(QLabel("Pick"))
        self._pick_spin = QSpinBox(self)
        self._pick_spin.setRange(1, 32)
        pick_row.addWidget(self._pick_spin)

        pick_row.addStretch(1)

        self._draft_button = PrimaryButton("Draft For My Team", self)
        self._draft_button.clicked.connect(self._handle_draft_pick)  # type: ignore[arg-type]
        pick_row.addWidget(self._draft_button)

        self._recap_model = QStandardItemModel(0, 5, self)
        self._recap_model.setHorizontalHeaderLabels([
            "Round",
            "Pick",
            "Team",
            "Player",
            "Grade",
        ])
        self._recap_table = QTableView(self)
        self._recap_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._recap_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._recap_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._recap_table.setAlternatingRowColors(True)
        self._recap_table.setModel(self._recap_model)
        draft_layout.addWidget(self._recap_table)

        export_row = QHBoxLayout()
        export_row.setSpacing(12)
        draft_layout.addLayout(export_row)

        self._export_class_button = SecondaryButton("Export Draft Class", self)
        self._export_class_button.clicked.connect(self._handle_export_class)  # type: ignore[arg-type]
        export_row.addWidget(self._export_class_button)

        self._export_results_button = SecondaryButton("Export Results", self)
        self._export_results_button.clicked.connect(self._handle_export_results)  # type: ignore[arg-type]
        export_row.addWidget(self._export_results_button)

        export_row.addStretch(1)
        layout.addWidget(draft_card)

        # Signals -------------------------------------------------------
        self._budget_slider.valueChanged.connect(self._on_budget_changed)
        self._budget_value.valueChanged.connect(self._on_budget_changed)
        self._position_filter.currentIndexChanged.connect(self._reload_prospects)
        self._watchlist_only.stateChanged.connect(lambda _: self._reload_prospects())
        team_store.teamChanged.connect(self._on_team_changed)

        self._reload_prospects()
        self._reload_board()
        self._reload_recap()
        self._update_budget_widgets(self._repo.get_budget())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _update_budget_widgets(self, value: int) -> None:
        self._budget_slider.blockSignals(True)
        self._budget_value.blockSignals(True)
        self._budget_slider.setValue(value)
        self._budget_value.setValue(value)
        self._clarity_bar.setValue(value)
        self._budget_slider.blockSignals(False)
        self._budget_value.blockSignals(False)

    def _on_budget_changed(self, value: int) -> None:
        new_value = self._repo.set_budget(int(value))
        self._update_budget_widgets(new_value)
        self._reload_prospects()

    def _on_team_changed(self, team: Optional[StoreTeamInfo]) -> None:
        self._our_team = team

    def _handle_toggle_watchlist(self, index) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        enabled = self._repo.toggle_watchlist(payload)
        self._set_status(
            f"{'Added' if enabled else 'Removed'} {index.data(Qt.ItemDataRole.DisplayRole)} from watchlist.",
            success=True,
        )
        self._reload_prospects()

    def _handle_tier_drop(self, prospect_id: str, tier: str, index: int) -> None:
        self._repo.assign_to_tier(prospect_id, tier, index=index if index >= 0 else None)
        self._reload_board()

    def _handle_remove_from_board(self, index) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole)
        if payload:
            self._repo.remove_from_board(payload)
            self._reload_board()

    def _handle_draft_pick(self) -> None:
        if not self._our_team:
            self._set_status("Select your franchise before drafting.", error=True)
            return
        selection = self._prospect_table.currentIndex()
        if not selection.isValid():
            self._set_status("Select a prospect to draft.", error=True)
            return
        prospect_id = selection.data(Qt.ItemDataRole.UserRole)
        round_number = int(self._round_spin.value())
        pick_index = int(self._pick_spin.value())
        team_info = TeamInfo(
            team_id=self._our_team.team_id,
            name=self._our_team.name,
            city=self._our_team.city,
            abbreviation=self._our_team.abbreviation,
        )
        result = self._repo.record_draft_pick(team_info, prospect_id, round_number, pick_index)
        if result is None:
            self._set_status("Prospect already drafted.", error=True)
            return
        self._reload_prospects()
        self._reload_board()
        self._reload_recap()
        self._event_bus.emit("depth_chart.changed", {"team_id": team_info.team_id})
        self._event_bus.emit("draft.pick.recorded", {"team_id": team_info.team_id, "prospect_id": prospect_id})
        self._set_status(
            f"Drafted {result.record.prospect_name} ({result.record.position}) at pick {result.record.pick_number}.",
            success=True,
        )

    # ------------------------------------------------------------------
    # Data reloads
    # ------------------------------------------------------------------

    def _handle_export_class(self) -> None:
        path = self._repo.export_draft_class()
        self._set_status(f"Draft class exported to {path.name}.", success=True)

    def _handle_export_results(self) -> None:
        path = self._repo.export_draft_results()
        self._set_status(f"Draft results exported to {path.name}.", success=True)

    def _reload_prospects(self) -> None:
        position = self._position_filter.currentData()
        watchlist_only = self._watchlist_only.isChecked()
        reports = self._repo.list_prospects(position=position, watchlist_only=watchlist_only)
        self._prospect_model.removeRows(0, self._prospect_model.rowCount())
        for report in reports:
            if report.drafted:
                continue
            metadata = report.prospect_id
            name_item = QStandardItem(report.name)
            name_item.setData(metadata, Qt.ItemDataRole.UserRole)
            items = [
                name_item,
                QStandardItem(report.position),
                QStandardItem(report.college),
                QStandardItem(report.archetype),
                QStandardItem(f"{report.grade:.1f}"),
                QStandardItem(f"R{report.projected_round}"),
                QStandardItem(report.combine_summary),
            ]
            self._prospect_model.appendRow(items)
        self._prospect_table.resizeColumnsToContents()

    def _reload_board(self) -> None:
        board = self._repo.get_board()
        for tier, widget in self._tier_rows.items():
            widget.blockSignals(True)
            widget.clear()
            for prospect_id in board.get(tier, []):
                profile = self._repo.get_prospect(prospect_id)
                label = prospect_id
                if profile:
                    label = f"{profile.name} ({profile.position})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, prospect_id)
                widget.addItem(item)
            widget.blockSignals(False)
    def _reload_recap(self) -> None:
        records = self._repo.list_draft_recap()
        self._recap_model.removeRows(0, self._recap_model.rowCount())
        for record in records:
            row = [
                QStandardItem(str(record.round_number)),
                QStandardItem(str(record.selection_index)),
                QStandardItem(record.team_name),
                QStandardItem(f"{record.prospect_name} ({record.position})"),
                QStandardItem(f"{record.grade:.1f}"),
            ]
            self._recap_model.appendRow(row)
        self._recap_table.resizeColumnsToContents()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._reload_prospects()
        self._reload_board()
        self._reload_recap()

    def _set_status(self, message: str, success: bool = False, error: bool = False) -> None:
        if error:
            self._status_label.setStyleSheet("color: #dc2626; font-weight: 600;")
        elif success:
            self._status_label.setStyleSheet("color: #16a34a; font-weight: 600;")
        else:
            self._status_label.setStyleSheet("")
        self._status_label.setText(message)

    def shutdown(self) -> None:
        pass
