from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDrag, QMimeData, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from domain.contracts import CapSummary
from domain.trades import (
    TradeAsset,
    TradeEvaluation,
    TradeRepository,
    TradeResult,
    TradeUndoResult,
)
from domain.teams import TeamInfo, TeamRepository
from ui.core import Card, EventBus, PrimaryButton, SecondaryButton
from ui.team.store import TeamInfo as StoreTeamInfo, TeamStore

TRADE_ASSET_MIME = "application/x-gridiron-trade-asset"


class TradeRosterTable(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.setDragEnabled(True)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:  # type: ignore[override]
        index = self.currentIndex()
        if not index.isValid():
            return
        payload = index.data(Qt.ItemDataRole.UserRole)
        if not payload:
            return
        mime = QMimeData()
        mime.setData(TRADE_ASSET_MIME, payload.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(supported_actions)


class TradeAssetList(QListWidget):
    def __init__(self, drop_callback, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drop_callback = drop_callback
        self.setAcceptDrops(True)
        self.setDragEnabled(False)

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if event.mimeData().hasFormat(TRADE_ASSET_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[override]
        data = event.mimeData().data(TRADE_ASSET_MIME)
        if not data:
            event.ignore()
            return
        self._drop_callback(bytes(data).decode("utf-8"))
        event.acceptProposedAction()


class TradeCenterPage(QWidget):
    """Trade center allowing human vs CPU offers with value meter."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        repository: Optional[TradeRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._trade_repo = repository or TradeRepository(user_home)
        self._team_repo = TeamRepository()
        self._our_team: Optional[StoreTeamInfo] = team_store.selected_team
        self._their_team: Optional[TeamInfo] = None
        self._our_assets: Dict[str, TradeAsset] = {}
        self._their_assets: Dict[str, TradeAsset] = {}
        self._offer_us: Dict[str, TradeAsset] = {}
        self._offer_them: Dict[str, TradeAsset] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Trade Center")
        header.setObjectName("coach-roster-title")
        layout.addWidget(header)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        team_row = QHBoxLayout()
        team_row.setSpacing(12)
        layout.addLayout(team_row)

        self._their_team_combo = QComboBox(self)
        team_row.addWidget(QLabel("Select Opponent:"))
        team_row.addWidget(self._their_team_combo)
        team_row.addStretch(1)

        self._value_bar = QProgressBar(self)
        self._value_bar.setRange(0, 200)
        self._value_bar.setValue(100)
        layout.addWidget(self._value_bar)

        self._value_label = QLabel("Value meter ready")
        layout.addWidget(self._value_label)

        split_layout = QGridLayout()
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(16)
        layout.addLayout(split_layout)

        # Our assets
        self._our_table = TradeRosterTable(self)
        self._our_model = QStandardItemModel(0, 4, self)
        self._our_model.setHorizontalHeaderLabels(["Player", "Pos", "OVR", "Value"])
        self._our_table.setModel(self._our_model)
        self._our_table.doubleClicked.connect(lambda index: self._handle_table_double_click(index, True))

        our_card = Card(self)
        our_layout = QVBoxLayout(our_card)
        our_layout.setContentsMargins(12, 12, 12, 12)
        our_layout.setSpacing(8)
        our_layout.addWidget(QLabel("Our Roster"))
        our_layout.addWidget(self._our_table)

        self._our_picks = QListWidget(self)
        self._our_picks.doubleClicked.connect(lambda index: self._handle_pick_double_click(index, True))
        our_layout.addWidget(QLabel("Our Draft Picks"))
        our_layout.addWidget(self._our_picks)

        split_layout.addWidget(our_card, 0, 0)

        # Their assets
        self._their_table = TradeRosterTable(self)
        self._their_model = QStandardItemModel(0, 4, self)
        self._their_model.setHorizontalHeaderLabels(["Player", "Pos", "OVR", "Value"])
        self._their_table.setModel(self._their_model)
        self._their_table.doubleClicked.connect(lambda index: self._handle_table_double_click(index, False))

        their_card = Card(self)
        their_layout = QVBoxLayout(their_card)
        their_layout.setContentsMargins(12, 12, 12, 12)
        their_layout.setSpacing(8)
        their_layout.addWidget(QLabel("Their Roster"))
        their_layout.addWidget(self._their_table)

        self._their_picks = QListWidget(self)
        self._their_picks.doubleClicked.connect(lambda index: self._handle_pick_double_click(index, False))
        their_layout.addWidget(QLabel("Their Draft Picks"))
        their_layout.addWidget(self._their_picks)

        split_layout.addWidget(their_card, 0, 2)

        # Offer lists
        offers_card = Card(self)
        offers_layout = QVBoxLayout(offers_card)
        offers_layout.setContentsMargins(12, 12, 12, 12)
        offers_layout.setSpacing(8)
        offers_layout.addWidget(QLabel("Proposed Trade"))

        offer_split = QHBoxLayout()
        offer_split.setSpacing(12)
        offers_layout.addLayout(offer_split)

        self._offer_us_list = TradeAssetList(lambda payload: self._handle_drop(payload, True), self)
        self._offer_us_list.doubleClicked.connect(lambda index: self._handle_offer_remove(index, True))
        offer_split.addWidget(self._wrap_offer_list("We send", self._offer_us_list))

        buttons_col = QVBoxLayout()
        self._evaluate_button = PrimaryButton("Evaluate Offer", self)
        self._evaluate_button.clicked.connect(self._handle_evaluate)  # type: ignore[arg-type]
        buttons_col.addWidget(self._evaluate_button)

        self._execute_button = PrimaryButton("Submit Trade", self)
        self._execute_button.clicked.connect(self._handle_execute)  # type: ignore[arg-type]
        buttons_col.addWidget(self._execute_button)

        self._undo_button = SecondaryButton("Undo Last Trade", self)
        self._undo_button.clicked.connect(self._handle_undo)  # type: ignore[arg-type]
        buttons_col.addWidget(self._undo_button)
        buttons_col.addStretch(1)
        offer_split.addLayout(buttons_col)

        self._offer_them_list = TradeAssetList(lambda payload: self._handle_drop(payload, False), self)
        self._offer_them_list.doubleClicked.connect(lambda index: self._handle_offer_remove(index, False))
        offer_split.addWidget(self._wrap_offer_list("They send", self._offer_them_list))

        split_layout.addWidget(offers_card, 0, 1)

        self._their_team_combo.currentIndexChanged.connect(self._on_their_team_changed)
        team_store.teamChanged.connect(self._on_team_changed)

        self._populate_their_team_options()
        if self._our_team and self._their_team:
            self._load_assets()
        else:
            self._set_status("Select a team to begin trading.", error=True)

    # Layout helpers ---------------------------------------------------
    def _wrap_offer_list(self, title: str, widget: QListWidget) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel(title))
        layout.addWidget(widget)
        return container

    # Data loading -----------------------------------------------------
    def _populate_their_team_options(self) -> None:
        teams = self._team_repo.list_teams()
        selected_id = self._their_team.team_id if self._their_team else None
        self._their_team_combo.blockSignals(True)
        self._their_team_combo.clear()
        for team in teams:
            if self._our_team and team.team_id == self._our_team.team_id:
                continue
            self._their_team_combo.addItem(team.display_name, team.team_id)
        self._their_team_combo.blockSignals(False)
        if self._their_team_combo.count() == 0:
            self._their_team = None
            return
        if selected_id is not None:
            index = self._their_team_combo.findData(selected_id)
            if index >= 0:
                self._their_team_combo.setCurrentIndex(index)
                self._their_team = next((t for t in teams if t.team_id == selected_id), None)
                return
        team_id = self._their_team_combo.currentData()
        self._their_team = next((team for team in teams if team.team_id == team_id), None)

    def _load_assets(self) -> None:
        if not self._our_team or not self._their_team:
            return
        our_assets = self._trade_repo.list_assets(self._our_team.team_id)
        their_assets = self._trade_repo.list_assets(self._their_team.team_id)
        self._our_assets = {
            asset.asset_id: asset
            for asset in our_assets["players"] + our_assets["picks"]
        }
        self._their_assets = {
            asset.asset_id: asset
            for asset in their_assets["players"] + their_assets["picks"]
        }
        self._populate_table(self._our_model, our_assets["players"])
        self._populate_table(self._their_model, their_assets["players"])
        self._populate_picks(self._our_picks, our_assets["picks"])
        self._populate_picks(self._their_picks, their_assets["picks"])
        self._offer_us.clear()
        self._offer_them.clear()
        self._offer_us_list.clear()
        self._offer_them_list.clear()
        self._refresh_value_meter()
        self._set_status("Select assets and evaluate the trade.")

    def _populate_table(self, model: QStandardItemModel, assets: List[TradeAsset]) -> None:
        model.removeRows(0, model.rowCount())
        for asset in assets:
            metadata = json.dumps({"asset_id": asset.asset_id})
            name_item = QStandardItem(asset.name)
            name_item.setData(metadata, Qt.ItemDataRole.UserRole)
            pos_item = QStandardItem(asset.metadata.get("position", ""))
            ovr_item = QStandardItem(asset.metadata.get("overall", ""))
            val_item = QStandardItem(f"{asset.value:.1f}")
            model.appendRow([name_item, pos_item, ovr_item, val_item])

    def _populate_picks(self, widget: QListWidget, assets: List[TradeAsset]) -> None:
        widget.clear()
        for asset in assets:
            item = QListWidgetItem(asset.name)
            item.setData(Qt.ItemDataRole.UserRole, json.dumps({"asset_id": asset.asset_id}))
            widget.addItem(item)

    # Event handlers ---------------------------------------------------
    def _on_team_changed(self, team: StoreTeamInfo | None) -> None:
        self._our_team = team
        self._populate_their_team_options()
        if self._our_team and self._their_team:
            self._load_assets()
        else:
            self._set_status("Select teams to begin trading.", error=True)
            self._refresh_value_meter()

    def _on_their_team_changed(self, index: int) -> None:
        team_id = self._their_team_combo.itemData(index)
        teams = self._team_repo.list_teams()
        self._their_team = next((team for team in teams if team.team_id == team_id), None)
        if self._our_team and self._their_team:
            self._load_assets()
        else:
            self._refresh_value_meter()

    def _handle_table_double_click(self, index, ours: bool) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole)
        if payload:
            data = json.loads(payload)
            self._add_asset_to_offer(data["asset_id"], ours)

    def _handle_pick_double_click(self, index, ours: bool) -> None:
        payload = index.data(Qt.ItemDataRole.UserRole)
        if payload:
            data = json.loads(payload)
            self._add_asset_to_offer(data["asset_id"], ours)

    def _handle_drop(self, payload: str, ours: bool) -> None:
        data = json.loads(payload)
        self._add_asset_to_offer(data["asset_id"], ours)

    def _handle_offer_remove(self, index, ours: bool) -> None:
        asset_id = index.data(Qt.ItemDataRole.UserRole)
        if asset_id:
            if ours:
                self._offer_us.pop(asset_id, None)
            else:
                self._offer_them.pop(asset_id, None)
            (self._offer_us_list if ours else self._offer_them_list).takeItem(index.row())
            self._refresh_value_meter()

    # Offer management -------------------------------------------------
    def _add_asset_to_offer(self, asset_id: str, ours: bool) -> None:
        asset_map = self._our_assets if ours else self._their_assets
        offer_map = self._offer_us if ours else self._offer_them
        offer_list = self._offer_us_list if ours else self._offer_them_list
        if asset_id not in asset_map or asset_id in offer_map:
            return
        asset = asset_map[asset_id]
        offer_map[asset_id] = asset
        item = QListWidgetItem(asset.name)
        item.setData(Qt.ItemDataRole.UserRole, asset_id)
        offer_list.addItem(item)
        self._refresh_value_meter()

    # Evaluate / execute -----------------------------------------------
    def _handle_evaluate(self) -> None:
        if not self._our_team or not self._their_team:
            self._set_status("Select both teams before evaluating.", error=True)
            return
        if not self._offer_us and not self._offer_them:
            self._set_status("Add assets to evaluate.", error=True)
            return
        evaluation = self._trade_repo.evaluate_trade(
            self._offer_us.values(),
            self._offer_them.values(),
        )
        self._show_evaluation(evaluation)

    def _show_evaluation(self, evaluation: TradeEvaluation, announce: bool = True) -> None:
        value = int(max(0, min(200, evaluation.balance_score * 200)))
        self._value_bar.setValue(value)
        balance = value / 2
        self._value_label.setText(
            f"Our value: {evaluation.our_value:.1f} | Their value: {evaluation.their_value:.1f} | Balance: {balance:.0f}"
        )
        if announce:
            self._set_status(evaluation.message, success=evaluation.accepted)

    def _handle_execute(self) -> None:
        if not self._our_team or not self._their_team:
            self._set_status("Select both teams before trading.", error=True)
            return
        if not self._offer_us and not self._offer_them:
            self._set_status("Select assets to trade.", error=True)
            return
        result: TradeResult = self._trade_repo.execute_trade(
            self._to_team_info(self._our_team),
            self._their_team,
            self._offer_us.values(),
            self._offer_them.values(),
        )
        self._after_trade_completed(result)

    def _after_trade_completed(self, result: TradeResult) -> None:
        self._offer_us.clear()
        self._offer_them.clear()
        self._offer_us_list.clear()
        self._offer_them_list.clear()
        self._load_assets()
        self._show_evaluation(result.evaluation, announce=False)
        self._set_status("Trade completed.", success=True)
        self._emit_cap_summary(result.our_team_id, result.our_summary)
        self._emit_cap_summary(result.their_team_id, result.their_summary)
        self._event_bus.emit(
            "trade.completed",
            {
                "our_team": result.our_team_id,
                "their_team": result.their_team_id,
            },
        )
        for team_id in (result.our_team_id, result.their_team_id):
            self._event_bus.emit("depth_chart.changed", {"team_id": team_id})

    def _handle_undo(self) -> None:
        undo_result: Optional[TradeUndoResult] = self._trade_repo.undo_last_trade()
        if not undo_result:
            self._set_status("Nothing to undo.", error=True)
            return
        self._offer_us.clear()
        self._offer_them.clear()
        self._offer_us_list.clear()
        self._offer_them_list.clear()
        self._load_assets()
        for team_id, summary in undo_result.summaries.items():
            self._emit_cap_summary(team_id, summary)
            self._event_bus.emit("depth_chart.changed", {"team_id": team_id})
        self._set_status("Trade undone.", success=True)

    def _refresh_value_meter(self) -> None:
        if not self._our_team or not self._their_team:
            self._value_bar.setValue(100)
            self._value_label.setText("Value meter ready")
            return
        if not self._offer_us and not self._offer_them:
            self._value_bar.setValue(100)
            self._value_label.setText("Value meter ready")
            return
        evaluation = self._trade_repo.evaluate_trade(
            self._offer_us.values(),
            self._offer_them.values(),
        )
        self._show_evaluation(evaluation, announce=False)

    # Utility ----------------------------------------------------------
    def _emit_cap_summary(self, team_id: Optional[str], summary: CapSummary) -> None:
        if not team_id:
            return
        self._event_bus.emit(
            "contract.changed",
            {
                "team_id": team_id,
                "cap_summary": summary.__dict__,
            },
        )

    def _set_status(self, message: str, success: bool = False, error: bool = False) -> None:
        if error:
            self._status_label.setStyleSheet("color: #dc2626; font-weight: 600;")
        elif success:
            self._status_label.setStyleSheet("color: #16a34a; font-weight: 600;")
        else:
            self._status_label.setStyleSheet("")
        self._status_label.setText(message)

    def refresh(self) -> None:
        self._refresh_value_meter()

    def shutdown(self) -> None:
        pass

    def _to_team_info(self, team: StoreTeamInfo) -> TeamInfo:
        return TeamInfo(
            team_id=team.team_id,
            name=team.name,
            city=team.city,
            abbreviation=team.abbreviation,
        )
