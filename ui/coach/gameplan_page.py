from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.core import Card, EventBus, PrimaryButton, SecondaryButton, Toast
from ui.team.store import TeamInfo, TeamStore
from domain.gameplan import (
    GameplanPreview,
    GameplanRepository,
    GameplanTendencies,
    SituationTendency,
    WeeklyGameplan,
)


class _SliderRow(QWidget):
    """Composite widget for a labeled slider with value preview."""

    def __init__(self, label: str, *, minimum: int = 0, maximum: int = 100, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._label = QLabel(label, self)
        self._label.setObjectName("form-row-label")
        layout.addWidget(self._label)
        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(minimum, maximum)
        self._slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self._slider.setSingleStep(1)
        layout.addWidget(self._slider, 1)
        self._value = QLabel("0%", self)
        self._value.setFixedWidth(44)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._value)
        self._slider.valueChanged.connect(lambda v: self._value.setText(f"{v}%"))

    @property
    def slider(self) -> QSlider:
        return self._slider

    def set_value(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._value.setText(f"{int(value)}%")
        self._slider.blockSignals(False)

    def value(self) -> int:
        return self._slider.value()


class WeeklyGameplanPage(QWidget):
    """Coach-facing UI for configuring weekly strategy and tendencies."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        repository: Optional[GameplanRepository] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._repository = repository or GameplanRepository(user_home)
        self._user_home = user_home
        self._current_plan: WeeklyGameplan | None = None
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._title = QLabel("Weekly Gameplan & Tendencies", self)
        self._title.setObjectName("coach-roster-title")
        layout.addWidget(self._title)

        self._subtitle = QLabel("Configure how you want to attack the upcoming opponent.", self)
        self._subtitle.setObjectName("section-subtitle")
        layout.addWidget(self._subtitle)

        header_row = QHBoxLayout()
        header_row.setSpacing(12)
        layout.addLayout(header_row)

        self._week_selector = QComboBox(self)
        for week in range(1, 19):
            self._week_selector.addItem(f"Week {week}", week)
        header_row.addWidget(self._week_selector)

        header_row.addStretch(1)

        self._import_button = SecondaryButton("Import Plan", self)
        header_row.addWidget(self._import_button)
        self._export_button = SecondaryButton("Export Plan", self)
        header_row.addWidget(self._export_button)
        self._save_button = PrimaryButton("Save Gameplan", self)
        header_row.addWidget(self._save_button)

        grid = QGridLayout()
        grid.setSpacing(16)
        layout.addLayout(grid, 1)

        self._tendency_card = Card(self)
        grid.addWidget(self._tendency_card, 0, 0)
        tendency_layout = QVBoxLayout(self._tendency_card)
        tendency_layout.setContentsMargins(16, 16, 16, 16)
        tendency_layout.setSpacing(12)
        tendency_layout.addWidget(QLabel("Call Tendency Sliders", self._tendency_card))

        self._run_slider = _SliderRow("Run Call Rate")
        self._deep_slider = _SliderRow("Deep Shot Rate")
        self._blitz_slider = _SliderRow("Blitz Rate")
        self._zone_slider = _SliderRow("Zone Coverage Rate")

        for slider in (self._run_slider, self._deep_slider, self._blitz_slider, self._zone_slider):
            tendency_layout.addWidget(slider)
            slider.slider.valueChanged.connect(self._mark_dirty)

        zone_hint = QLabel("Man coverage rate automatically mirrors the inverse of zone.")
        zone_hint.setProperty("component", "tag")
        tendency_layout.addWidget(zone_hint)

        self._preview_card = Card(self)
        grid.addWidget(self._preview_card, 1, 0)
        preview_layout = QVBoxLayout(self._preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(8)

        preview_header = QHBoxLayout()
        preview_layout.addLayout(preview_header)
        preview_header.addWidget(QLabel("Simulate Tendencies", self._preview_card))
        preview_header.addStretch(1)
        self._simulate_button = PrimaryButton("Sim 10 test drives", self._preview_card)
        preview_header.addWidget(self._simulate_button)

        self._preview_summary = QLabel("Run a preview to see expected tendencies.", self._preview_card)
        self._preview_summary.setWordWrap(True)
        preview_layout.addWidget(self._preview_summary)

        self._situation_card = Card(self)
        grid.addWidget(self._situation_card, 0, 1, 2, 1)
        situation_layout = QVBoxLayout(self._situation_card)
        situation_layout.setContentsMargins(16, 16, 16, 16)
        situation_layout.setSpacing(12)

        situation_header = QHBoxLayout()
        situation_layout.addLayout(situation_header)
        situation_header.addWidget(QLabel("Situational Preferences", self._situation_card))
        situation_header.addStretch(1)
        self._add_row_button = SecondaryButton("Add Row", self._situation_card)
        situation_header.addWidget(self._add_row_button)
        self._remove_row_button = SecondaryButton("Remove Row", self._situation_card)
        situation_header.addWidget(self._remove_row_button)

        self._situation_table = QTableWidget(0, 4, self._situation_card)
        self._situation_table.setHorizontalHeaderLabels(["Situation", "Primary", "Secondary", "Notes"])
        self._situation_table.horizontalHeader().setStretchLastSection(True)
        self._situation_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._situation_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        situation_layout.addWidget(self._situation_table, 1)

        self._notes_card = Card(self)
        layout.addWidget(self._notes_card)
        notes_layout = QVBoxLayout(self._notes_card)
        notes_layout.setContentsMargins(16, 16, 16, 16)
        notes_layout.setSpacing(8)
        notes_layout.addWidget(QLabel("Coaching Notes", self._notes_card))
        self._notes_edit = QTextEdit(self._notes_card)
        self._notes_edit.setPlaceholderText("Scouting insights, matchup alerts, situational reminders...")
        notes_layout.addWidget(self._notes_edit)
        self._notes_edit.textChanged.connect(self._mark_dirty)

        self._scout_card = Card(self)
        layout.addWidget(self._scout_card)
        scout_layout = QVBoxLayout(self._scout_card)
        scout_layout.setContentsMargins(16, 16, 16, 16)
        scout_layout.setSpacing(8)
        scout_layout.addWidget(QLabel("Opponent Scouting Report", self._scout_card))
        self._scout_summary = QLabel("Select a team to load scouting intel.", self._scout_card)
        self._scout_summary.setWordWrap(True)
        scout_layout.addWidget(self._scout_summary)
        self._scout_details = QLabel("", self._scout_card)
        self._scout_details.setWordWrap(True)
        scout_layout.addWidget(self._scout_details)

        self._week_selector.currentIndexChanged.connect(lambda _: self._reload())
        self._save_button.clicked.connect(self._handle_save)
        self._simulate_button.clicked.connect(self._handle_simulate)
        self._import_button.clicked.connect(self._handle_import)
        self._export_button.clicked.connect(self._handle_export)
        self._add_row_button.clicked.connect(self._handle_add_row)
        self._remove_row_button.clicked.connect(self._handle_remove_row)
        self._situation_table.itemChanged.connect(lambda *_: self._mark_dirty())

        team_store.teamChanged.connect(self._on_team_changed)
        if team_store.selected_team:
            self._reload(team_store.selected_team)

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def shutdown(self) -> None:  # pragma: no cover - symmetry with other pages
        pass

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _on_team_changed(self, team: TeamInfo | None) -> None:
        self._reload(team)

    def _reload(self, team: TeamInfo | None = None) -> None:
        current_team = team or self._team_store.selected_team
        if current_team is None:
            self._subtitle.setText("Select a team to configure the weekly gameplan.")
            self._current_plan = None
            self._clear_ui()
            return
        week = int(self._week_selector.currentData())
        plan = self._repository.load_plan(current_team.team_id, week=week)
        self._current_plan = plan
        self._dirty = False
        self._populate_ui(plan)
        self._refresh_subtitle(current_team)

    def _clear_ui(self) -> None:
        self._run_slider.set_value(50)
        self._deep_slider.set_value(40)
        self._blitz_slider.set_value(25)
        self._zone_slider.set_value(60)
        self._preview_summary.setText("Run a preview to see expected tendencies.")
        self._situation_table.setRowCount(0)
        self._notes_edit.blockSignals(True)
        self._notes_edit.clear()
        self._notes_edit.blockSignals(False)
        self._scout_summary.setText("Select a team to load scouting intel.")
        self._scout_details.setText("")

    def _populate_ui(self, plan: WeeklyGameplan) -> None:
        tendencies = plan.tendencies
        self._run_slider.set_value(tendencies.run_rate)
        self._deep_slider.set_value(tendencies.deep_shot_rate)
        self._blitz_slider.set_value(tendencies.blitz_rate)
        self._zone_slider.set_value(tendencies.zone_rate)
        self._notes_edit.blockSignals(True)
        self._notes_edit.setPlainText(plan.notes)
        self._notes_edit.blockSignals(False)
        self._populate_situations(plan)
        self._refresh_preview_summary(None)
        self._populate_scouting(plan)

    def _populate_situations(self, plan: WeeklyGameplan) -> None:
        self._situation_table.blockSignals(True)
        self._situation_table.setRowCount(0)
        for situation in plan.situations:
            self._append_situation_row(situation)
        self._situation_table.blockSignals(False)

    def _populate_scouting(self, plan: WeeklyGameplan) -> None:
        team = self._team_store.selected_team
        if team is None:
            self._scout_summary.setText("Select a team to load scouting intel.")
            self._scout_details.setText("")
            return
        report = self._repository.scouting_report(team.team_id, plan.opponent_id, week=plan.week)
        self._scout_summary.setText(
            f"{report.opponent.display_name} - Record {report.record} | Offense #{report.offense_rank} | Defense #{report.defense_rank}"
        )
        details = [
            f"Explosive play rate: {report.explosive_rate:.1%}",
            f"Pressure allowed: {report.pressure_rate_allowed:.1%}",
            "Last five: " + ", ".join(report.last_five_results),
            "Key players: " + ", ".join(report.key_players),
            f"Gameplan tip: {report.narrative}",
        ]
        self._scout_details.setText("\n".join(details))

    def _append_situation_row(self, situation: SituationTendency | None = None) -> None:
        row = self._situation_table.rowCount()
        self._situation_table.insertRow(row)
        entries = [
            situation.bucket if situation else "",
            situation.primary_call if situation else "",
            situation.secondary_call if situation else "",
            situation.notes if situation else "",
        ]
        for column, value in enumerate(entries):
            item = QTableWidgetItem(value)
            self._situation_table.setItem(row, column, item)

    def _gather_situations(self) -> List[SituationTendency]:
        rows: List[SituationTendency] = []
        for row in range(self._situation_table.rowCount()):
            bucket = self._cell_text(row, 0)
            primary = self._cell_text(row, 1)
            secondary = self._cell_text(row, 2)
            notes = self._cell_text(row, 3)
            if not bucket and not primary and not secondary:
                continue
            rows.append(
                SituationTendency(
                    bucket=bucket or "Situation",
                    primary_call=primary or "Call",
                    secondary_call=secondary or "",
                    notes=notes,
                )
            )
        return rows

    def _cell_text(self, row: int, column: int) -> str:
        item = self._situation_table.item(row, column)
        if item is None:
            return ""
        return item.text().strip()

    def _collect_plan(self) -> WeeklyGameplan | None:
        if self._current_plan is None:
            return None
        plan = WeeklyGameplan(
            team_id=self._current_plan.team_id,
            opponent_id=self._current_plan.opponent_id,
            week=self._current_plan.week,
            tendencies=GameplanTendencies(
                run_rate=self._run_slider.value(),
                deep_shot_rate=self._deep_slider.value(),
                blitz_rate=self._blitz_slider.value(),
                zone_rate=self._zone_slider.value(),
            ),
            situations=self._gather_situations(),
            notes=self._notes_edit.toPlainText().strip(),
        )
        return plan

    def _refresh_preview_summary(self, preview: GameplanPreview | None) -> None:
        if preview is None:
            self._preview_summary.setText("Run a preview to see expected tendencies.")
            return
        total_plays = preview.expected_run_calls + preview.expected_pass_calls
        man_calls = max(0, total_plays - preview.expected_zone_calls)
        summary = (
            f"Projected {total_plays} plays across {preview.drives} drives. "
            f"Run {preview.expected_run_calls} / Pass {preview.expected_pass_calls} (Deep shots ~{preview.expected_deep_shots}).\n"
            f"Defense: Blitz {preview.expected_blitz_calls}, Zone {preview.expected_zone_calls} (Man {man_calls}).\n"
            f"Explosive play chance {preview.explosive_play_chance:.1%} | Takeaway chance {preview.takeaway_chance:.1%} | Expected points {preview.expected_points:.1f}"
        )
        self._preview_summary.setText(summary)

    def _refresh_subtitle(self, team: TeamInfo | None) -> None:
        if self._current_plan is None or team is None:
            self._subtitle.setText("Select a team to configure the weekly gameplan.")
            return
        text = f"{team.display_name} vs {self._current_plan.opponent_id} (Week {self._current_plan.week})"
        if self._dirty:
            text += " *"
        self._subtitle.setText(text)

    def _mark_dirty(self, *_: object) -> None:
        if self._current_plan is None:
            return
        self._dirty = True
        self._refresh_subtitle(self._team_store.selected_team)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------
    def _handle_save(self) -> None:
        plan = self._collect_plan()
        if plan is None:
            return
        saved = self._repository.save_plan(plan)
        self._current_plan = saved
        self._dirty = False
        self._refresh_subtitle(self._team_store.selected_team)
        Toast.show_message(self, "Gameplan saved.")
        self._event_bus.emit(
            "gameplan.updated",
            {
                "team_id": saved.team_id,
                "opponent_id": saved.opponent_id,
                "week": saved.week,
                "tendencies": saved.tendencies.to_dict(),
            },
        )

    def _handle_simulate(self) -> None:
        plan = self._collect_plan()
        if plan is None:
            QMessageBox.warning(self, "Gameplan", "Select a team before running a preview.")
            return
        preview = self._repository.preview(plan, drives=10)
        self._refresh_preview_summary(preview)

    def _handle_import(self) -> None:
        team = self._team_store.selected_team
        if team is None or self._current_plan is None:
            QMessageBox.warning(self, "Import Gameplan", "Select a team before importing a gameplan.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Gameplan",
            str((self._user_home / "exports").resolve()),
            "Gameplan Files (*.json)",
        )
        if not path:
            return
        try:
            imported = self._repository.import_plan(
                Path(path),
                override_ids=(team.team_id, self._current_plan.opponent_id, self._current_plan.week),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Gameplan", f"Unable to import plan: {exc}")
            return
        self._current_plan = imported
        self._dirty = False
        self._populate_ui(imported)
        self._refresh_subtitle(team)
        Toast.show_message(self, "Gameplan imported.")

    def _handle_export(self) -> None:
        plan = self._collect_plan()
        if plan is None:
            QMessageBox.warning(self, "Export Gameplan", "Select a team before exporting a gameplan.")
            return
        default_name = f"{plan.team_id}_wk{plan.week}_{plan.opponent_id}.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Gameplan",
            str((self._user_home / "exports" / default_name).resolve()),
            "Gameplan Files (*.json)",
        )
        if not path:
            return
        try:
            self._repository.export_plan(plan, Path(path))
        except OSError as exc:
            QMessageBox.critical(self, "Export Gameplan", f"Unable to export plan: {exc}")
            return
        Toast.show_message(self, "Gameplan exported.")

    def _handle_add_row(self) -> None:
        self._append_situation_row()
        self._mark_dirty()

    def _handle_remove_row(self) -> None:
        selected = self._situation_table.currentRow()
        if selected < 0:
            return
        self._situation_table.removeRow(selected)
        self._mark_dirty()


__all__ = ["WeeklyGameplanPage"]
