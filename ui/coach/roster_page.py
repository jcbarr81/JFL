from __future__ import annotations

from pathlib import Path
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDrag, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ui.core import Card, EventBus
from domain.roster import (
    DEPTH_CHART_TEMPLATE,
    DepthSlot,
    DepthUnitEnum,
    RosterPlayer,
    RosterRepository,
    slots_by_unit,
)
from ui.team.store import TeamInfo, TeamStore

PLAYER_MIME_TYPE = "application/x-gridiron-player"


class RosterTableView(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setDragEnabled(True)
        self.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)

    def startDrag(self, supportedActions: Qt.DropActions) -> None:  # type: ignore[override]
        index = self.currentIndex()
        if not index.isValid():
            return
        player_id = index.data(Qt.ItemDataRole.UserRole)
        if not player_id:
            return
        mime = QMimeData()
        mime.setData(PLAYER_MIME_TYPE, player_id.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supportedActions)


class DepthSlotWidget(Card):
    def __init__(self, slot: DepthSlot, roster_lookup: Dict[str, RosterPlayer], drop_callback, parent=None):
        super().__init__(parent)
        self._slot = slot
        self._roster_lookup = roster_lookup
        self._drop_callback = drop_callback
        self.setAcceptDrops(True)
        self.setMinimumWidth(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        self._title = QLabel(f"{slot.role}")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)
        self._player_label = QLabel("--")
        self._player_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._player_label)
        self.refresh()

    @property
    def slot(self) -> DepthSlot:
        return self._slot

    def refresh(self) -> None:
        player = self._roster_lookup.get(self._slot.player_id or "")
        self._player_label.setText(player.name if player else "Empty")

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(PLAYER_MIME_TYPE):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        data = event.mimeData().data(PLAYER_MIME_TYPE)
        if not data:
            event.ignore()
            return
        player_id = bytes(data).decode("utf-8")
        self._drop_callback(self._slot, player_id)
        event.acceptProposedAction()


class RosterManagementPage(QWidget):
    """Roster table and depth chart management interface."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        repository: Optional[RosterRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._repository = repository or RosterRepository(user_home)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending: Future | None = None
        self._players: Dict[str, RosterPlayer] = {}
        self._slots: List[DepthSlot] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Roster & Depth Chart")
        header.setObjectName("coach-roster-title")
        header.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(header)

        self._validation_label = QLabel("")
        self._validation_label.setObjectName("coach-roster-validation")
        layout.addWidget(self._validation_label)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        layout.addLayout(filter_row)

        filter_row.addWidget(QLabel("Position:"))
        self._position_filter = QComboBox(self)
        self._position_filter.addItem("All", None)
        for unit_slots in DEPTH_CHART_TEMPLATE.values():
            for _, position, _ in unit_slots:
                if self._position_filter.findData(position.value) == -1:
                    self._position_filter.addItem(position.value, position.value)
        self._position_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._position_filter)

        filter_row.addWidget(QLabel("Age:"))
        self._age_filter = QComboBox(self)
        self._age_filter.addItems(["All", "< 26", "26-30", "31+"])
        self._age_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._age_filter)

        filter_row.addWidget(QLabel("Contract:"))
        self._contract_filter = QComboBox(self)
        self._contract_filter.addItems(["All", "Active", "Expiring"])
        self._contract_filter.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._contract_filter)

        filter_row.addWidget(QLabel("Search:"))
        self._search_filter = QLineEdit(self)
        self._search_filter.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self._search_filter)
        filter_row.addStretch(1)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)
        layout.addLayout(content_layout)

        roster_card = Card(self)
        roster_layout = QVBoxLayout(roster_card)
        roster_layout.setContentsMargins(12, 12, 12, 12)
        roster_layout.setSpacing(8)
        roster_layout.addWidget(QLabel("Roster"))
        self._roster_view = RosterTableView(roster_card)
        roster_layout.addWidget(self._roster_view)
        content_layout.addWidget(roster_card, 1)

        depth_card = Card(self)
        depth_layout = QVBoxLayout(depth_card)
        depth_layout.setContentsMargins(12, 12, 12, 12)
        depth_layout.setSpacing(8)
        depth_layout.addWidget(QLabel("Depth Chart"))
        self._depth_container = QWidget(depth_card)
        self._depth_grid = QGridLayout(self._depth_container)
        self._depth_grid.setSpacing(12)
        depth_layout.addWidget(self._depth_container)

        buttons_row = QHBoxLayout()
        self._auto_fix_button = QPushButton("Auto-Fix", depth_card)
        self._auto_fix_button.clicked.connect(self._handle_auto_fix)  # type: ignore[arg-type]
        buttons_row.addWidget(self._auto_fix_button)
        buttons_row.addStretch(1)
        depth_layout.addLayout(buttons_row)

        content_layout.addWidget(depth_card, 1)

        self._model = QStandardItemModel(0, 5, self)
        self._model.setHorizontalHeaderLabels(["Name", "Pos", "#", "OVR", "Age"])
        self._roster_view.setModel(self._model)
        self._roster_view.horizontalHeader().setStretchLastSection(True)

        team_store.teamChanged.connect(self._on_team_changed)
        if team_store.selected_team:
            self._load_team(team_store.selected_team)

    def shutdown(self) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_team_changed(self, team: TeamInfo | None) -> None:
        if team is None:
            self._players.clear()
            self._slots.clear()
            self._model.removeRows(0, self._model.rowCount())
            self._validation_label.setText("Select a team to manage the roster.")
            return
        self._load_team(team)

    def _load_team(self, team: TeamInfo) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._validation_label.setText(f"Loading roster for {team.display_name}...")
        future = self._executor.submit(self._load_data, team.team_id)
        self._pending = future
        future.add_done_callback(lambda f: self._apply_loaded(team, f))

    def _load_data(self, team_id: str) -> tuple[List[RosterPlayer], List[DepthSlot]]:
        players = self._repository.list_players(team_id)
        slots = self._repository.load_depth_chart(team_id)
        return players, slots

    def _apply_loaded(self, team: TeamInfo, future: Future) -> None:
        if future.cancelled():
            return
        try:
            players, slots = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            self._validation_label.setText(f"Unable to load roster: {exc}")
            return
        self._players = {player.player_id: player for player in players}
        self._slots = slots
        self._populate_roster_table(players)
        self._populate_depth_chart(slots)
        self._update_validation(team)

    def _populate_roster_table(self, players: List[RosterPlayer]) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for player in players:
            name_item = QStandardItem(player.name)
            name_item.setData(player.player_id, Qt.ItemDataRole.UserRole)
            pos_item = QStandardItem(player.position.value)
            jersey_item = QStandardItem(str(player.jersey_number))
            ovr_item = QStandardItem(str(player.overall))
            age = 22 + abs(hash(player.player_id)) % 15
            age_item = QStandardItem(str(age))
            self._model.appendRow([name_item, pos_item, jersey_item, ovr_item, age_item])
        self._apply_filters()

    def _populate_depth_chart(self, slots: List[DepthSlot]) -> None:
        # Clear existing widgets
        while self._depth_grid.count():
            item = self._depth_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        grouped = slots_by_unit(slots)
        row = 0
        for unit in DepthUnitEnum:
            title = QLabel(unit.value.replace("_", " ").title())
            title.setProperty("component", "tag")
            self._depth_grid.addWidget(title, row, 0, 1, len(grouped.get(unit, [])) or 1)
            row += 1
            col = 0
            for slot in grouped.get(unit, []):
                widget = DepthSlotWidget(slot, self._players, self._handle_slot_drop, self._depth_container)
                self._depth_grid.addWidget(widget, row, col)
                col += 1
            row += 1

    def _handle_slot_drop(self, slot: DepthSlot, player_id: str) -> None:
        team = self._team_store.selected_team
        if team is None:
            return
        slot.player_id = player_id
        self._repository.save_depth_chart(team.team_id, self._slots)
        self._event_bus.emit("depth_chart.changed", {
            "team_id": team.team_id,
            "slot": slot.role,
            "player_id": player_id,
        })
        self._populate_depth_chart(self._slots)
        self._update_validation(team)

    def _apply_filters(self) -> None:
        position = self._position_filter.currentData()
        age_filter = self._age_filter.currentText()
        contract_filter = self._contract_filter.currentText()
        search_term = self._search_filter.text().lower()
        for row in range(self._model.rowCount()):
            player_id = self._model.item(row, 0).data(Qt.ItemDataRole.UserRole)
            visible = True
            pos_value = self._model.item(row, 1).text()
            if position and pos_value != position:
                visible = False
            age = int(self._model.item(row, 4).text())
            if age_filter == "< 26" and age >= 26:
                visible = False
            elif age_filter == "26-30" and not (26 <= age <= 30):
                visible = False
            elif age_filter == "31+" and age < 31:
                visible = False
            if contract_filter == "Expiring" and hash(player_id) % 2 == 0:
                visible = False
            if contract_filter == "Active" and hash(player_id) % 2 != 0:
                visible = False if contract_filter != "All" else visible
            if search_term and search_term not in self._model.item(row, 0).text().lower():
                visible = False
            self._roster_view.setRowHidden(row, not visible)

    def _handle_auto_fix(self) -> None:
        team = self._team_store.selected_team
        if team is None:
            return
        self._validation_label.setText("Running auto-fix...")
        future = self._executor.submit(self._repository.auto_fix, team.team_id)
        future.add_done_callback(lambda f: self._apply_auto_fix(team, f))

    def _apply_auto_fix(self, team: TeamInfo, future: Future) -> None:
        if future.cancelled():
            return
        try:
            slots = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            self._validation_label.setText(f"Auto-fix failed: {exc}")
            return
        self._slots = slots
        self._populate_depth_chart(slots)
        self._update_validation(team)
        self._event_bus.emit("depth_chart.changed", {
            "team_id": team.team_id,
            "auto_fix": True,
        })

    def _update_validation(self, team: TeamInfo | None) -> None:
        if team is None:
            self._validation_label.setText("Select a team to manage the roster.")
            self._validation_label.setStyleSheet("")
            return
        warnings = self._repository.validate(team.team_id, self._slots)
        if warnings:
            self._validation_label.setText("; ".join(warnings))
            self._validation_label.setStyleSheet("color: #f59e0b; font-weight: 600;")
        else:
            self._validation_label.setText("Depth chart valid.")
            self._validation_label.setStyleSheet("color: #16a34a; font-weight: 600;")

