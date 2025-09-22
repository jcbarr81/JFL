from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QTabWidget,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from domain.models import Play
from domain.playbook import (
    PlayFilters,
    PlaySummary,
    PlayValidationError,
    PlaybookError,
    PlaybookRepository,
)
from ui.core import Card, EventBus, PrimaryButton, SecondaryButton, StatePlaceholder, Toast, ValuePill
from ui.team.store import TeamInfo, TeamStore


class PlayPreviewCanvas(QWidget):
    """Lightweight visualizer that sketches routes for the selected play."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._play: Play | None = None
        self._play_type: str = "offense"
        self.setMinimumHeight(220)
        self.setMinimumWidth(320)

    def set_play(self, play: Play | None, play_type: str) -> None:
        self._play = play
        self._play_type = play_type
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(12, 12, -12, -12)
        painter.fillRect(rect, QColor("#0B6623"))

        yard_pen = QPen(QColor("#14532d"))
        yard_pen.setWidth(1)
        painter.setPen(yard_pen)
        for index in range(0, 61, 5):
            y = rect.bottom() - (index / 60.0) * rect.height()
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        hash_pen = QPen(QColor("#1f2937"))
        hash_pen.setWidth(1)
        painter.setPen(hash_pen)
        for tick in range(1, 60):
            y = rect.bottom() - (tick / 60.0) * rect.height()
            painter.drawLine(rect.left() + rect.width() * 0.05, int(y), rect.right() - rect.width() * 0.05, int(y))

        if not self._play:
            return

        route_pen = QPen(QColor("#fef08a" if self._play_type == "offense" else "#93c5fd"))
        route_pen.setWidth(2)
        painter.setPen(route_pen)

        for assignment in self._play.assignments:
            if not assignment.route:
                continue
            points = [self._map_point(point.x, point.y, rect) for point in assignment.route]
            if not points:
                continue
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)
            painter.setBrush(QColor("#facc15") if self._play_type == "offense" else QColor("#60a5fa"))
            painter.drawEllipse(points[0], 4, 4)
            painter.drawEllipse(points[-1], 3, 3)

    def _map_point(self, x: float, y: float, rect) -> QPointF:
        clamped_x = max(-26.5, min(26.5, x))
        clamped_y = max(0.0, min(60.0, y))
        px = rect.left() + ((clamped_x + 26.5) / 53.0) * rect.width()
        py = rect.bottom() - (clamped_y / 60.0) * rect.height()
        return QPointF(px, py)


class PlayDetailPanel(Card):
    """Displays metadata, success metrics, and a diagram preview for the current play."""

    def __init__(
        self,
        *,
        save_tags: Callable[[str, List[str]], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._save_tags = save_tags
        self._summary: PlaySummary | None = None
        self._play: Play | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._title = QLabel("Select a play")
        self._title.setObjectName("play-detail-title")
        layout.addWidget(self._title)

        self._meta_label = QLabel("")
        self._meta_label.setObjectName("play-detail-meta")
        layout.addWidget(self._meta_label)

        self._tags_label = QLabel("Tags: --")
        layout.addWidget(self._tags_label)

        self._preview = PlayPreviewCanvas(self)
        layout.addWidget(self._preview, 1)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(6)
        layout.addLayout(metrics)

        self._success_pill = ValuePill("Success: --")
        self._calls_pill = ValuePill("Calls: --")
        self._avg_gain_pill = ValuePill("Avg Gain: --")
        metrics.addWidget(self._success_pill, 0, 0)
        metrics.addWidget(self._calls_pill, 0, 1)
        metrics.addWidget(self._avg_gain_pill, 0, 2)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        self._tag_input = QLineEdit(self)
        self._tag_input.setPlaceholderText("Tags (comma separated)")
        tag_row.addWidget(self._tag_input, 1)
        self._save_tags_button = SecondaryButton("Save Tags", self)
        self._save_tags_button.clicked.connect(self._apply_tags)  # type: ignore[arg-type]
        tag_row.addWidget(self._save_tags_button)
        layout.addLayout(tag_row)

    def set_content(self, summary: PlaySummary | None, play: Play | None) -> None:
        self._summary = summary
        self._play = play
        if summary is None:
            self._title.setText("Select a play")
            self._meta_label.setText("")
            self._tags_label.setText("Tags: --")
            self._success_pill.setText("Success: --")
            self._calls_pill.setText("Calls: --")
            self._avg_gain_pill.setText("Avg Gain: --")
            self._tag_input.setText("")
            self._preview.set_play(None, "offense")
            return

        self._title.setText(summary.name)
        meta_bits = [summary.formation, summary.personnel, f"v{summary.version}"]
        if summary.last_modified:
            meta_bits.append(summary.last_modified.strftime("%Y-%m-%d %H:%M"))
        self._meta_label.setText(" | ".join(meta_bits))
        tags_text = ", ".join(summary.tags) if summary.tags else "--"
        self._tags_label.setText(f"Tags: {tags_text}")
        self._tag_input.setText(", ".join(summary.tags))

        success_pct = summary.usage.success_rate * 100.0
        self._success_pill.setText(f"Success: {success_pct:.1f}%")
        self._calls_pill.setText(f"Calls: {summary.usage.calls}")
        self._avg_gain_pill.setText(f"Avg Gain: {summary.usage.avg_gain:.1f}")
        self._preview.set_play(play, summary.play_type)

    def _apply_tags(self) -> None:
        if self._summary is None:
            return
        raw = self._tag_input.text()
        tags = [part.strip() for part in raw.split(",") if part.strip()]
        self._save_tags(self._summary.play_id, tags)


class PlaybookTab(QWidget):
    """Single tab that lists either offense or defense plays."""

    def __init__(
        self,
        play_type: str,
        repository: PlaybookRepository,
        team_store: TeamStore,
        event_bus: EventBus,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._play_type = play_type
        self._repository = repository
        self._team_store = team_store
        self._event_bus = event_bus
        self._summaries: List[PlaySummary] = []
        self._filters = PlayFilters()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._formation_filter = QComboBox(self)
        self._formation_filter.addItem("All formations", None)
        self._formation_filter.currentIndexChanged.connect(self._on_filters_changed)
        filter_row.addWidget(self._formation_filter)

        self._personnel_filter = QComboBox(self)
        self._personnel_filter.addItem("All personnel", None)
        self._personnel_filter.currentIndexChanged.connect(self._on_filters_changed)
        filter_row.addWidget(self._personnel_filter)

        self._tag_filter = QComboBox(self)
        self._tag_filter.addItem("All tags", None)
        self._tag_filter.currentIndexChanged.connect(self._on_filters_changed)
        filter_row.addWidget(self._tag_filter)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search plays")
        self._search.textChanged.connect(self._on_filters_changed)
        filter_row.addWidget(self._search, 1)

        root.addLayout(filter_row)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        root.addWidget(self._splitter, 1)

        list_container = QWidget(self._splitter)
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)

        self._table_model = QStandardItemModel(0, 7, self)
        self._table_model.setHorizontalHeaderLabels(
            [
                "Play",
                "Formation",
                "Personnel",
                "Tags",
                "Calls",
                "Success %",
                "Version",
            ]
        )
        self._table = QTableView(list_container)
        self._table.setModel(self._table_model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self._table.setSortingEnabled(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)  # type: ignore[arg-type]
        list_layout.addWidget(self._table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._export_button = SecondaryButton("Export", self)
        self._export_button.clicked.connect(self._export_selected)  # type: ignore[arg-type]
        actions.addWidget(self._export_button)

        self._mirror_button = SecondaryButton("Mirror", self)
        self._mirror_button.clicked.connect(self._mirror_selected)
        actions.addWidget(self._mirror_button)

        self._editor_button = SecondaryButton("Open in Editor", self)
        self._editor_button.clicked.connect(self._open_in_editor)
        actions.addWidget(self._editor_button)

        actions.addStretch(1)

        self._assign_button = PrimaryButton("Add to Gameplan", self)
        self._assign_button.clicked.connect(self._assign_to_gameplan)
        actions.addWidget(self._assign_button)

        list_layout.addLayout(actions)

        self._detail_panel = PlayDetailPanel(save_tags=self._save_tags, parent=self._splitter)
        self._splitter.addWidget(list_container)
        self._splitter.addWidget(self._detail_panel)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 2)

        self._placeholder = StatePlaceholder(
            "No plays yet",
            "Import plays or create new ones in the editor.",
            parent=self,
        )
        self._placeholder.hide()

        self.refresh()

    # ------------------------------------------------------------------
    # Data loading & refresh
    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._summaries = self._repository.list_plays(self._play_type)
        self._populate_filters()
        self._apply_filters()

    def _populate_filters(self) -> None:
        formations = sorted({item.formation for item in self._summaries})
        personnel = sorted({item.personnel for item in self._summaries})
        tags = sorted({tag for item in self._summaries for tag in item.tags})
        self._rebuild_combo(self._formation_filter, formations, "All formations")
        self._rebuild_combo(self._personnel_filter, personnel, "All personnel")
        self._rebuild_combo(self._tag_filter, tags, "All tags")

    def _rebuild_combo(self, combo: QComboBox, items: List[str], empty_label: str) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(empty_label, None)
        for value in items:
            combo.addItem(value, value)
        if current in items:
            index = combo.findData(current)
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _apply_filters(self) -> None:
        filters = PlayFilters(
            formation=self._formation_filter.currentData(),
            personnel=self._personnel_filter.currentData(),
            tag=self._tag_filter.currentData(),
            search=self._search.text().strip() or None,
        )
        self._filters = filters
        filtered = [item for item in self._summaries if self._matches(item, filters)]
        self._populate_table(filtered)

    def _matches(self, summary: PlaySummary, filters: PlayFilters) -> bool:
        if filters.formation and summary.formation != filters.formation:
            return False
        if filters.personnel and summary.personnel != filters.personnel:
            return False
        if filters.tag and filters.tag not in summary.tags:
            return False
        if filters.search:
            haystack = " ".join(
                [
                    summary.name,
                    summary.play_id,
                    summary.formation,
                    summary.personnel,
                    " ".join(summary.tags),
                ]
            ).lower()
            if filters.search.lower() not in haystack:
                return False
        return True

    def _populate_table(self, summaries: List[PlaySummary]) -> None:
        self._table_model.removeRows(0, self._table_model.rowCount())
        for summary in summaries:
            row = [
                QStandardItem(summary.name),
                QStandardItem(summary.formation),
                QStandardItem(summary.personnel),
                QStandardItem(", ".join(summary.tags)),
                QStandardItem(str(summary.usage.calls)),
                QStandardItem(f"{summary.usage.success_rate * 100.0:.1f}"),
                QStandardItem(str(summary.version)),
            ]
            for item in row:
                item.setEditable(False)
            row[0].setData(summary.play_id, Qt.ItemDataRole.UserRole)
            self._table_model.appendRow(row)
        is_empty = self._table_model.rowCount() == 0
        self._placeholder.setVisible(is_empty)
        self._table.setEnabled(not is_empty)
        self._export_button.setEnabled(not is_empty)
        self._mirror_button.setEnabled(not is_empty)
        self._editor_button.setEnabled(not is_empty)
        self._assign_button.setEnabled(not is_empty)
        if not is_empty:
            self._table.selectRow(0)
            index = self._table_model.index(0, 0)
            self._reveal_summary(index.data(Qt.ItemDataRole.UserRole))
        else:
            self._detail_panel.set_content(None, None)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_filters_changed(self, *_args) -> None:
        self._apply_filters()

    def _on_selection_changed(self, *_args) -> None:
        index = self._table.currentIndex()
        play_id = index.data(Qt.ItemDataRole.UserRole)
        self._reveal_summary(play_id)

    def _reveal_summary(self, play_id: Optional[str]) -> None:
        if not play_id:
            self._detail_panel.set_content(None, None)
            return
        summary = next((item for item in self._summaries if item.play_id == play_id), None)
        if summary is None:
            self._detail_panel.set_content(None, None)
            return
        try:
            play, _ = self._repository.load_play(play_id)
        except PlayValidationError:
            play = None
        self._detail_panel.set_content(summary, play)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _export_selected(self) -> None:
        summary = self._current_summary()
        if summary is None:
            return
        default_name = summary.play_id + ".json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Play",
            default_name,
            "Play Files (*.json)",
        )
        if not path:
            return
        try:
            dest = self._repository.export_play(summary.play_id, Path(path))
        except PlaybookError as exc:
            QMessageBox.critical(self, "Export Play", str(exc))
            return
        Toast.show_message(self, f"Exported to {dest}")

    def _mirror_selected(self) -> None:
        summary = self._current_summary()
        if summary is None:
            return
        mirrored = self._repository.mirror_play(summary.play_id)
        Toast.show_message(self, f"Created {mirrored.play_id}")
        self.refresh()

    def _open_in_editor(self) -> None:
        summary = self._current_summary()
        if summary is None:
            return
        self._event_bus.emit("playbook.open_editor", summary.play_id)
        Toast.show_message(self, "Opening editor...")

    def _assign_to_gameplan(self) -> None:
        summary = self._current_summary()
        team = self._team_store.selected_team
        if summary is None or team is None:
            return
        payload = {
            "team_id": team.team_id,
            "play_id": summary.play_id,
            "play_type": summary.play_type,
        }
        self._event_bus.emit("gameplan.play.attached", payload)
        Toast.show_message(self, f"Queued {summary.name} for {team.abbreviation}")

    def _save_tags(self, play_id: str, tags: List[str]) -> None:
        self._repository.update_tags(play_id, tags)
        self.refresh()
        self._event_bus.emit("playbook.tags.updated", {"play_id": play_id, "tags": tags})

    def _current_summary(self) -> Optional[PlaySummary]:
        index = self._table.currentIndex()
        play_id = index.data(Qt.ItemDataRole.UserRole)
        return next((item for item in self._summaries if item.play_id == play_id), None)


class PlaybookManagerPage(QWidget):
    """Top-level page that wraps offense and defense tabs and coordinates shared actions."""

    def __init__(
        self,
        team_store: TeamStore,
        event_bus: EventBus,
        user_home: Path,
        *,
        plays_dir: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._team_store = team_store
        self._event_bus = event_bus
        self._repository = PlaybookRepository(plays_dir=plays_dir, user_home=user_home)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Playbook Manager")
        header.setObjectName("coach-roster-title")
        layout.addWidget(header)

        self._subtitle = QLabel("Curate offensive and defensive playbooks for weekly plans.")
        self._subtitle.setObjectName("section-subtitle")
        layout.addWidget(self._subtitle)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._import_button = PrimaryButton("Import Play", self)
        self._import_button.clicked.connect(self._import_play)  # type: ignore[arg-type]
        action_row.addWidget(self._import_button)

        self._refresh_button = SecondaryButton("Refresh", self)
        self._refresh_button.clicked.connect(self._refresh_tabs)
        action_row.addWidget(self._refresh_button)

        action_row.addStretch(1)
        layout.addLayout(action_row)

        self._tabs = QTabWidget(self)
        self._offense_tab = PlaybookTab("offense", self._repository, team_store, event_bus, parent=self)
        self._defense_tab = PlaybookTab("defense", self._repository, team_store, event_bus, parent=self)
        self._tabs.addTab(self._offense_tab, "Offense")
        self._tabs.addTab(self._defense_tab, "Defense")
        layout.addWidget(self._tabs, 1)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        team_store.teamChanged.connect(self._on_team_changed)
        self._update_subtitle(team_store.selected_team)

    def _import_play(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import Play",
            str(Path("data/plays").resolve()),
            "Play Files (*.json)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            play = self._repository.import_play_file(path, overwrite=False)
        except PlayValidationError as exc:
            QMessageBox.critical(self, "Import Play", f"Validation failed: {exc.errors}")
            return
        except PlaybookError as exc:
            QMessageBox.critical(self, "Import Play", str(exc))
            return
        Toast.show_message(self, f"Imported {play.play_id}")
        self._refresh_tabs()
        self._event_bus.emit("playbook.imported", play.play_id)

    def _refresh_tabs(self) -> None:
        self._offense_tab.refresh()
        self._defense_tab.refresh()

    def _on_tab_changed(self, index: int) -> None:
        self._update_subtitle(self._team_store.selected_team)

    def _on_team_changed(self, team: TeamInfo | None) -> None:
        self._update_subtitle(team)

    def _update_subtitle(self, team: TeamInfo | None) -> None:
        scope = "Offense" if self._tabs.currentIndex() == 0 else "Defense"
        if team is None:
            self._subtitle.setText(f"Select a team to curate {scope.lower()} playbooks.")
        else:
            self._subtitle.setText(f"{scope} playbook for {team.display_name}.")


__all__ = ["PlaybookManagerPage"]

