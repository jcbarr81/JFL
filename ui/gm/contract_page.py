from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ui.core import Card, EventBus, PrimaryButton, SecondaryButton
from domain.contracts import CAP_LIMIT, CapSummary, ContractRecord, ContractsRepository
from ui.team.store import TeamInfo, TeamStore


class ContractsManagementPage(QWidget):
    """Contracts and salary cap management interface."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        repository: Optional[ContractsRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._repository = repository or ContractsRepository(user_home)
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending: Future | None = None
        self._contracts: Dict[str, ContractRecord] = {}
        self._current_contract: ContractRecord | None = None
        self._summary: CapSummary | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Contracts & Salary Cap")
        header.setObjectName("coach-roster-title")
        layout.addWidget(header)

        self._summary_card = Card(self)
        summary_layout = QHBoxLayout(self._summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(12)
        self._summary_label = QLabel("Cap information unavailable")
        summary_layout.addWidget(self._summary_label)
        summary_layout.addStretch(1)

        self._export_button = SecondaryButton("Export CSV", self._summary_card)
        self._export_button.clicked.connect(self._handle_export)  # type: ignore[arg-type]
        summary_layout.addWidget(self._export_button)

        self._auto_button = SecondaryButton("Auto Restructure", self._summary_card)
        self._auto_button.clicked.connect(self._handle_auto_restructure)  # type: ignore[arg-type]
        summary_layout.addWidget(self._auto_button)

        layout.addWidget(self._summary_card)

        self._validation_label = QLabel("")
        self._validation_label.setObjectName("coach-roster-validation")
        layout.addWidget(self._validation_label)

        content_row = QHBoxLayout()
        content_row.setSpacing(16)
        layout.addLayout(content_row)

        table_card = Card(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        table_layout.addWidget(QLabel("Contracts"))
        self._table = QTableView(table_card)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        table_layout.addWidget(self._table)
        content_row.addWidget(table_card, 3)

        editor_card = Card(self)
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(12, 12, 12, 12)
        editor_layout.setSpacing(8)
        editor_layout.addWidget(QLabel("Edit Contract"))

        editor_layout.addWidget(QLabel("Years"))
        self._years_spin = QSpinBox(editor_card)
        self._years_spin.setRange(1, 7)
        editor_layout.addWidget(self._years_spin)

        editor_layout.addWidget(QLabel("Base Salary (Millions)"))
        self._salary_spin = QDoubleSpinBox(editor_card)
        self._salary_spin.setRange(0.0, 300.0)
        self._salary_spin.setSuffix(" M")
        self._salary_spin.setDecimals(2)
        editor_layout.addWidget(self._salary_spin)

        editor_layout.addWidget(QLabel("Signing Bonus (Millions)"))
        self._bonus_spin = QDoubleSpinBox(editor_card)
        self._bonus_spin.setRange(0.0, 200.0)
        self._bonus_spin.setSuffix(" M")
        self._bonus_spin.setDecimals(2)
        editor_layout.addWidget(self._bonus_spin)

        editor_layout.addWidget(QLabel("Status"))
        self._status_combo = QComboBox(editor_card)
        self._status_combo.addItems(["Active", "Injured", "Released"])
        editor_layout.addWidget(self._status_combo)

        self._apply_button = PrimaryButton("Apply Changes", editor_card)
        self._apply_button.clicked.connect(self._handle_apply)  # type: ignore[arg-type]
        editor_layout.addWidget(self._apply_button)
        editor_layout.addStretch(1)
        content_row.addWidget(editor_card, 2)

        self._model = QStandardItemModel(0, 6, self)
        self._model.setHorizontalHeaderLabels(["Player", "Pos", "Years", "Base", "Bonus", "Cap Hit"])
        self._table.setModel(self._model)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.selectionModel().currentChanged.connect(self._on_selection_changed)

        team_store.teamChanged.connect(self._on_team_changed)
        if team_store.selected_team:
            self._load_team(team_store.selected_team)

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _on_team_changed(self, team: TeamInfo | None) -> None:
        if team is None:
            self._contracts.clear()
            self._model.removeRows(0, self._model.rowCount())
            self._summary_label.setText("Select a team to view contracts.")
            self._summary_label.setStyleSheet("")
            self._validation_label.setText("")
            return
        self._load_team(team)

    def _load_team(self, team: TeamInfo) -> None:
        if self._pending and not self._pending.done():
            self._pending.cancel()
        self._summary_label.setText(f"Loading contracts for {team.display_name}...")
        future = self._executor.submit(self._repository.list_contracts, team.team_id)
        self._pending = future
        future.add_done_callback(lambda f: self._apply_loaded(team, f))

    def _apply_loaded(self, team: TeamInfo, future: Future) -> None:
        if future.cancelled():
            return
        try:
            contracts = future.result()
        except Exception as exc:  # pragma: no cover - defensive
            self._summary_label.setText(f"Unable to load contracts: {exc}")
            self._summary_label.setStyleSheet("color: #dc2626; font-weight: 600;")
            return
        self._contracts = {contract.contract_id: contract for contract in contracts}
        self._populate_table(contracts)
        self._update_summary(team)
        self._validation_label.setText("")

    def _populate_table(self, contracts: List[ContractRecord]) -> None:
        self._model.removeRows(0, self._model.rowCount())
        for contract in contracts:
            items = [
                QStandardItem(contract.player_name),
                QStandardItem(contract.position),
                QStandardItem(str(contract.years)),
                QStandardItem(f"${contract.base_salary/1_000_000:.2f}M"),
                QStandardItem(f"${contract.signing_bonus/1_000_000:.2f}M"),
                QStandardItem(f"${contract.cap_hit/1_000_000:.2f}M"),
            ]
            items[0].setData(contract.contract_id, Qt.ItemDataRole.UserRole)
            for item in items:
                item.setEditable(False)
            self._model.appendRow(items)
        if contracts:
            self._table.selectRow(0)

    def _on_selection_changed(self, current, _previous) -> None:
        if not current or not current.isValid():
            self._current_contract = None
            return
        contract_id = current.siblingAtColumn(0).data(Qt.ItemDataRole.UserRole)
        contract = self._contracts.get(contract_id)
        if contract is None:
            self._current_contract = None
            return
        self._current_contract = contract
        self._years_spin.setValue(contract.years)
        self._salary_spin.setValue(contract.base_salary / 1_000_000)
        self._bonus_spin.setValue(contract.signing_bonus / 1_000_000)
        idx = self._status_combo.findText(contract.status)
        if idx == -1:
            idx = 0
        self._status_combo.setCurrentIndex(idx)

    def _handle_apply(self) -> None:
        team = self._team_store.selected_team
        if team is None or self._current_contract is None:
            return
        updated = ContractRecord(
            contract_id=self._current_contract.contract_id,
            player_id=self._current_contract.player_id,
            team_id=team.team_id,
            player_name=self._current_contract.player_name,
            position=self._current_contract.position,
            years=self._years_spin.value(),
            base_salary=self._salary_spin.value() * 1_000_000,
            signing_bonus=self._bonus_spin.value() * 1_000_000,
            signing_year=self._current_contract.signing_year,
            status=self._status_combo.currentText(),
        )
        try:
            summary = self._repository.update_contract(updated)
        except ValueError as exc:
            self._validation_label.setText(str(exc))
            self._validation_label.setStyleSheet("color: #dc2626; font-weight: 600;")
            return
        self._contracts[updated.contract_id] = updated
        self._refresh_row(updated)
        self._update_summary(team, summary)
        self._validation_label.setText("Contract updated.")
        self._validation_label.setStyleSheet("color: #16a34a; font-weight: 600;")
        self._event_bus.emit("contract.changed", {
            "team_id": team.team_id,
            "cap_summary": {
                "limit": summary.cap_limit,
                "used": summary.cap_used,
                "available": summary.cap_available,
            },
        })
        self._event_bus.emit("dashboard.reload", {
            "cards": {
                "cap_room": {
                    "summary": f"${summary.cap_available/1_000_000:.1f}M",
                    "details": [
                        f"Cap used: ${summary.cap_used/1_000_000:.1f}M",
                        f"Dead money: ${summary.dead_money/1_000_000:.1f}M",
                    ],
                }
            }
        })

    def _refresh_row(self, contract: ContractRecord) -> None:
        for row in range(self._model.rowCount()):
            if self._model.item(row, 0).data(Qt.ItemDataRole.UserRole) == contract.contract_id:
                self._model.item(row, 2).setText(str(contract.years))
                self._model.item(row, 3).setText(f"${contract.base_salary/1_000_000:.2f}M")
                self._model.item(row, 4).setText(f"${contract.signing_bonus/1_000_000:.2f}M")
                self._model.item(row, 5).setText(f"${contract.cap_hit/1_000_000:.2f}M")
                break

    def _update_summary(self, team: TeamInfo, summary: Optional[CapSummary] = None) -> None:
        summary = summary or self._repository.calculate_cap_summary(team.team_id)
        self._summary = summary
        self._summary_label.setText(
            f"Cap Limit: ${summary.cap_limit/1_000_000:.1f}M | Used: ${summary.cap_used/1_000_000:.1f}M | "
            f"Dead: ${summary.dead_money/1_000_000:.1f}M | Available: ${summary.cap_available/1_000_000:.1f}M"
        )
        if summary.cap_available < 0:
            self._summary_label.setStyleSheet("color: #dc2626; font-weight: 600;")
            self._apply_button.setEnabled(False)
        else:
            self._summary_label.setStyleSheet("")
            self._apply_button.setEnabled(True)

    def _handle_auto_restructure(self) -> None:
        team = self._team_store.selected_team
        if team is None:
            return
        summary = self._repository.auto_restructure(team.team_id)
        self._contracts = {c.contract_id: c for c in self._repository.list_contracts(team.team_id)}
        self._populate_table(list(self._contracts.values()))
        self._update_summary(team, summary)
        self._validation_label.setText("Auto restructure complete.")
        self._validation_label.setStyleSheet("color: #16a34a; font-weight: 600;")

    def _handle_export(self) -> None:
        team = self._team_store.selected_team
        if team is None:
            return
        path = self._repository.export_cap_table(team.team_id)
        self._validation_label.setText(f"Exported cap table to {path}")
        self._validation_label.setStyleSheet("color: #9ca3af;")

