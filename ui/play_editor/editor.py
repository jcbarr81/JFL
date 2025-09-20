from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from typing import Callable, Dict, Iterable, List, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.api.plays import _validate_play
from domain.models import Play
from pydantic import ValidationError

# Constants for the editable field.
FIELD_HALF_WIDTH = 26.5
FIELD_LENGTH = 60.0
PIXELS_PER_YARD = 6.0
TOKEN_RADIUS = 6.0
ROUTE_ROLES = {"route", "defend", "rush"}
ALL_ROLES = [
    "pass",
    "carry",
    "block",
    "route",
    "defend",
    "rush",
    "kick",
    "hold",
]


@dataclass
class Waypoint:
    timestamp: float
    x: float
    y: float

    def as_json(self) -> Dict[str, float]:
        return {
            "timestamp": round(self.timestamp, 3),
            "x": round(self.x, 3),
            "y": round(self.y, 3),
        }


@dataclass
class PlayerState:
    player_id: str
    role: str
    anchor_x: float
    anchor_y: float
    waypoints: List[Waypoint] = field(default_factory=list)


class FieldGeometry:
    def field_to_scene(self, x: float, y: float) -> QPointF:
        sx = (x + FIELD_HALF_WIDTH) * PIXELS_PER_YARD
        sy = (FIELD_LENGTH - y) * PIXELS_PER_YARD
        return QPointF(sx, sy)

    def scene_to_field(self, point: QPointF) -> tuple[float, float]:
        x = (point.x() / PIXELS_PER_YARD) - FIELD_HALF_WIDTH
        y = FIELD_LENGTH - (point.y() / PIXELS_PER_YARD)
        return x, y

    def clamp(self, x: float, y: float) -> tuple[float, float]:
        clamped_x = min(FIELD_HALF_WIDTH, max(-FIELD_HALF_WIDTH, x))
        clamped_y = min(FIELD_LENGTH, max(0.0, y))
        return clamped_x, clamped_y

    def scene_rect(self) -> QRectF:
        width = (FIELD_HALF_WIDTH * 2) * PIXELS_PER_YARD
        height = FIELD_LENGTH * PIXELS_PER_YARD
        return QRectF(0.0, 0.0, width, height)


class FieldScene(QGraphicsScene):
    def __init__(self, geometry: FieldGeometry) -> None:
        super().__init__(geometry.scene_rect())
        self._geometry = geometry
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)

    def drawBackground(self, painter, rect):  # type: ignore[override]
        painter.fillRect(self.sceneRect(), QColor("#0B6623"))
        pen_major = QPen(QColor("#FFFFFF"))
        pen_major.setWidthF(1.4)
        pen_minor = QPen(QColor("#DDDDDD"))
        pen_minor.setWidthF(0.6)

        # Vertical yard lines every 5 yards, hash marks each yard.
        for yard in range(-25, 26):
            x = (yard + FIELD_HALF_WIDTH) * PIXELS_PER_YARD
            pen = pen_major if yard % 5 == 0 else pen_minor
            painter.setPen(pen)
            painter.drawLine(x, 0.0, x, FIELD_LENGTH * PIXELS_PER_YARD)

        # Horizontal grid every 5 yards.
        for yard in range(0, int(FIELD_LENGTH) + 1, 5):
            y = (FIELD_LENGTH - yard) * PIXELS_PER_YARD
            painter.setPen(pen_major if yard % 10 == 0 else pen_minor)
            painter.drawLine(0.0, y, self.sceneRect().width(), y)


class PlayerItem(QGraphicsEllipseItem):
    def __init__(
        self,
        player_id: str,
        geometry: FieldGeometry,
        on_move: Callable[[str, float, float], None],
    ) -> None:
        super().__init__(
            -TOKEN_RADIUS,
            -TOKEN_RADIUS,
            TOKEN_RADIUS * 2,
            TOKEN_RADIUS * 2,
        )
        self.player_id = player_id
        self._geometry = geometry
        self._on_move = on_move
        self.setBrush(QColor("#F5F5F5"))
        self.setPen(QPen(QColor("#222222")))
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsEllipseItem.GraphicsItemFlag.ItemSendsGeometryChanges, True
        )
        self.setZValue(2.0)
        label = QGraphicsSimpleTextItem(player_id, self)
        label.setBrush(QColor("#222222"))
        label.setPos(-label.boundingRect().width() / 2, -22)

    def itemChange(self, change, value):  # type: ignore[override]
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionChange:
            point: QPointF = value
            x, y = self._geometry.scene_to_field(point)
            x, y = self._geometry.clamp(x, y)
            return self._geometry.field_to_scene(x, y)
        if change == QGraphicsEllipseItem.GraphicsItemChange.ItemPositionHasChanged:
            x, y = self._geometry.scene_to_field(self.pos())
            self._on_move(self.player_id, x, y)
        return super().itemChange(change, value)


class MetadataWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QFormLayout(self)
        self.play_id = QLineEdit()
        self.name = QLineEdit()
        self.formation = QLineEdit()
        self.personnel = QLineEdit()
        self.play_type = QComboBox()
        self.play_type.addItems(["offense", "defense", "special_teams"])
        layout.addRow("Play ID", self.play_id)
        layout.addRow("Name", self.name)
        layout.addRow("Formation", self.formation)
        layout.addRow("Personnel", self.personnel)
        layout.addRow("Play Type", self.play_type)

    def set_metadata(self, data: dict[str, str]) -> None:
        self.play_id.setText(data.get("play_id", ""))
        self.name.setText(data.get("name", ""))
        self.formation.setText(data.get("formation", ""))
        self.personnel.setText(data.get("personnel", ""))
        play_type = data.get("play_type", "offense")
        index = self.play_type.findText(play_type)
        self.play_type.setCurrentIndex(max(0, index))

    def metadata(self) -> dict[str, str]:
        return {
            "play_id": self.play_id.text().strip(),
            "name": self.name.text().strip(),
            "formation": self.formation.text().strip(),
            "personnel": self.personnel.text().strip(),
            "play_type": self.play_type.currentText(),
        }


class PlayerPanel(QWidget):
    def __init__(self, editor: "PlayEditor") -> None:
        super().__init__()
        self._editor = editor
        self._state: PlayerState | None = None

        layout = QVBoxLayout(self)
        self.player_label = QLabel("Select a player")
        layout.addWidget(self.player_label)

        self.role_combo = QComboBox()
        self.role_combo.addItems(ALL_ROLES)
        self.role_combo.currentTextChanged.connect(self._on_role_changed)
        layout.addWidget(self.role_combo)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Time", "X", "Y"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        controls = QFormLayout()
        self.timestamp_spin = QDoubleSpinBox()
        self.timestamp_spin.setRange(0.0, 15.0)
        self.timestamp_spin.setDecimals(2)
        self.timestamp_spin.setSingleStep(0.1)
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-FIELD_HALF_WIDTH, FIELD_HALF_WIDTH)
        self.x_spin.setDecimals(2)
        self.x_spin.setSingleStep(0.5)
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(0.0, FIELD_LENGTH)
        self.y_spin.setDecimals(2)
        self.y_spin.setSingleStep(0.5)
        controls.addRow("Timestamp", self.timestamp_spin)
        controls.addRow("X", self.x_spin)
        controls.addRow("Y", self.y_spin)
        controls_widget = QWidget()
        controls_widget.setLayout(controls)
        layout.addWidget(controls_widget)

        button_row = QVBoxLayout()
        add_btn = QPushButton("Add Waypoint")
        add_btn.clicked.connect(self._on_add_waypoint)
        button_row.addWidget(add_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove_waypoint)
        button_row.addWidget(remove_btn)

        anchor_btn = QPushButton("Use Token Start")
        anchor_btn.clicked.connect(self._on_anchor_waypoint)
        button_row.addWidget(anchor_btn)

        button_container = QWidget()
        button_container.setLayout(button_row)
        layout.addWidget(button_container)

        layout.addStretch(1)
        self._update_enabled(False)

    def set_state(self, state: PlayerState | None) -> None:
        self._state = state
        if not state:
            self.player_label.setText("Select a player")
            self.table.setRowCount(0)
            self._update_enabled(False)
            return

        self._update_enabled(True)
        self.player_label.setText(f"Player: {state.player_id}")
        index = self.role_combo.findText(state.role)
        self.role_combo.blockSignals(True)
        self.role_combo.setCurrentIndex(max(0, index))
        self.role_combo.blockSignals(False)
        self._refresh_table()
        self.x_spin.setValue(state.anchor_x)
        self.y_spin.setValue(state.anchor_y)
        self.timestamp_spin.setValue(0.0)
        self._toggle_route_controls(state.role)

    def _toggle_route_controls(self, role: str) -> None:
        enable = role in ROUTE_ROLES
        self.table.setEnabled(enable)
        self.timestamp_spin.setEnabled(enable)
        self.x_spin.setEnabled(True)
        self.y_spin.setEnabled(True)

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        if not self._state:
            return
        for waypoint in self._state.waypoints:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(f"{waypoint.timestamp:.2f}"))
            self.table.setItem(row, 1, QTableWidgetItem(f"{waypoint.x:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{waypoint.y:.2f}"))

    def _update_enabled(self, enabled: bool) -> None:
        self.role_combo.setEnabled(enabled)
        self.table.setEnabled(enabled)
        self.timestamp_spin.setEnabled(enabled)
        self.x_spin.setEnabled(enabled)
        self.y_spin.setEnabled(enabled)

    def _on_role_changed(self, role: str) -> None:
        if not self._state:
            return
        self._toggle_route_controls(role)
        self._editor.update_player_role(self._state.player_id, role)
        self._refresh_table()

    def _on_add_waypoint(self) -> None:
        if not self._state:
            return
        timestamp = float(self.timestamp_spin.value())
        x = float(self.x_spin.value())
        y = float(self.y_spin.value())
        self._editor.add_waypoint(self._state.player_id, timestamp, x, y)
        self._refresh_table()

    def _on_remove_waypoint(self) -> None:
        if not self._state:
            return
        row = self.table.currentRow()
        if row <= 0:
            QMessageBox.information(self, "Remove Waypoint", "Select a waypoint beyond the anchor to remove.")
            return
        self._editor.remove_waypoint(self._state.player_id, row)
        self._refresh_table()

    def _on_anchor_waypoint(self) -> None:
        if not self._state:
            return
        self._editor.snap_anchor_to_token(self._state.player_id)
        self._refresh_table()


class PlayEditor(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Gridiron Play Editor")
        self.geometry = FieldGeometry()
        self.scene = FieldScene(self.geometry)
        self.view = QGraphicsView(self.scene)
        self.setCentralWidget(self.view)

        self.metadata_widget = MetadataWidget()
        metadata_dock = QDockWidget("Play Metadata")
        metadata_dock.setWidget(self.metadata_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, metadata_dock)

        self.player_panel = PlayerPanel(self)
        player_dock = QDockWidget("Player Editor")
        player_dock.setWidget(self.player_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, player_dock)

        self._states: dict[str, PlayerState] = {}
        self._items: dict[str, PlayerItem] = {}
        self._player_order: list[str] = []
        self._current_path: Path | None = None
        self._suspend_token_updates = False

        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.new_action = QAction("New", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self.new_play)
        toolbar.addAction(self.new_action)

        self.open_action = QAction("Open", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_play)
        toolbar.addAction(self.open_action)

        self.save_action = QAction("Save", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self.save_play)
        toolbar.addAction(self.save_action)

        self.save_as_action = QAction("Save As", self)
        self.save_as_action.triggered.connect(self.save_play_as)
        toolbar.addAction(self.save_as_action)

        self.mirror_action = QAction("Mirror Left/Right", self)
        self.mirror_action.setShortcut("Ctrl+M")
        self.mirror_action.triggered.connect(self.mirror_play)
        toolbar.addAction(self.mirror_action)

        self.validate_action = QAction("Validate", self)
        self.validate_action.setShortcut("Ctrl+Shift+V")
        self.validate_action.triggered.connect(self.validate_current_play)
        toolbar.addAction(self.validate_action)

        self.scene.selectionChanged.connect(self._handle_selection_changed)
        self.new_play()

    # region Player manipulation helpers
    def _clear_players(self) -> None:
        for item in self._items.values():
            self.scene.removeItem(item)
        self._states.clear()
        self._items.clear()
        self._player_order.clear()
        self.player_panel.set_state(None)

    def _create_player(
        self,
        player_id: str,
        role: str,
        anchor_x: float,
        anchor_y: float,
        waypoints: Optional[Iterable[Waypoint]] = None,
    ) -> None:
        anchor_x, anchor_y = self.geometry.clamp(anchor_x, anchor_y)
        item = PlayerItem(player_id, self.geometry, self._on_player_moved)
        item.setPos(self.geometry.field_to_scene(anchor_x, anchor_y))
        self.scene.addItem(item)
        state = PlayerState(
            player_id=player_id,
            role=role,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            waypoints=list(waypoints or []),
        )
        if state.role in ROUTE_ROLES:
            self._ensure_anchor_waypoint(state)
        self._states[player_id] = state
        self._items[player_id] = item
        self._player_order.append(player_id)

    def _ensure_anchor_waypoint(self, state: PlayerState) -> None:
        if not state.waypoints:
            state.waypoints.append(Waypoint(0.0, state.anchor_x, state.anchor_y))
        else:
            anchor = state.waypoints[0]
            anchor.timestamp = 0.0
            anchor.x = state.anchor_x
            anchor.y = state.anchor_y
            state.waypoints.sort(key=lambda wp: wp.timestamp)

    def _on_player_moved(self, player_id: str, x: float, y: float) -> None:
        if self._suspend_token_updates:
            return
        state = self._states.get(player_id)
        if not state:
            return
        state.anchor_x, state.anchor_y = self.geometry.clamp(x, y)
        if state.role in ROUTE_ROLES:
            self._ensure_anchor_waypoint(state)
        if self.player_panel._state and self.player_panel._state.player_id == player_id:
            self.player_panel.set_state(state)

    def update_player_role(self, player_id: str, role: str) -> None:
        state = self._states[player_id]
        state.role = role
        if role in ROUTE_ROLES:
            self._ensure_anchor_waypoint(state)
        else:
            state.waypoints.clear()
        if self.player_panel._state and self.player_panel._state.player_id == player_id:
            self.player_panel.set_state(state)

    def add_waypoint(self, player_id: str, timestamp: float, x: float, y: float) -> None:
        state = self._states[player_id]
        if state.role not in ROUTE_ROLES:
            return
        self._ensure_anchor_waypoint(state)
        waypoint = Waypoint(timestamp, *self.geometry.clamp(x, y))
        # Replace existing waypoint with same timestamp.
        for existing in state.waypoints:
            if abs(existing.timestamp - waypoint.timestamp) < 1e-6:
                existing.x = waypoint.x
                existing.y = waypoint.y
                break
        else:
            state.waypoints.append(waypoint)
        state.waypoints.sort(key=lambda wp: wp.timestamp)

    def remove_waypoint(self, player_id: str, index: int) -> None:
        state = self._states[player_id]
        if state.role not in ROUTE_ROLES:
            return
        if 0 < index < len(state.waypoints):
            state.waypoints.pop(index)

    def snap_anchor_to_token(self, player_id: str) -> None:
        state = self._states[player_id]
        item = self._items[player_id]
        x, y = self.geometry.scene_to_field(item.pos())
        state.anchor_x, state.anchor_y = self.geometry.clamp(x, y)
        if state.role in ROUTE_ROLES:
            self._ensure_anchor_waypoint(state)

    # endregion

    def _handle_selection_changed(self) -> None:
        selected = self.scene.selectedItems()
        if not selected:
            self.player_panel.set_state(None)
            return
        item = selected[0]
        if isinstance(item, PlayerItem):
            state = self._states[item.player_id]
            self.player_panel.set_state(state)

    def serialize_play(self) -> dict[str, object]:
        payload = self.metadata_widget.metadata()
        assignments: List[dict[str, object]] = []
        for player_id in self._player_order:
            state = self._states[player_id]
            route_payload: Optional[List[dict[str, float]]] = None
            if state.waypoints:
                if state.role not in ROUTE_ROLES:
                    route_payload = None
                elif len(state.waypoints) < 2:
                    raise ValueError(
                        f"Player '{player_id}' requires at least two waypoints for role '{state.role}'"
                    )
                else:
                    route_payload = [waypoint.as_json() for waypoint in state.waypoints]
            assignment = {
                "player_id": state.player_id,
                "role": state.role,
                "route": route_payload,
            }
            assignments.append(assignment)
        payload["assignments"] = assignments
        return payload

    def validate_current_play(self, show_dialog: bool = True) -> bool:
        try:
            data = self.serialize_play()
        except ValueError as exc:
            if show_dialog:
                QMessageBox.warning(self, "Validation", str(exc))
            return False
        try:
            play = Play.model_validate(data)
        except ValidationError as exc:
            if show_dialog:
                QMessageBox.warning(
                    self,
                    "Validation",
                    "\n".join(error["msg"] for error in exc.errors()),
                )
            return False
        errors = _validate_play(play)
        if errors:
            if show_dialog:
                message = "\n".join(error.get("msg", "Unknown error") for error in errors)
                QMessageBox.warning(self, "Validation", message)
            return False
        if show_dialog:
            QMessageBox.information(self, "Validation", "Play is valid.")
        return True

    def new_play(self) -> None:
        self._clear_players()
        defaults = [
            ("QB1", "pass", 0.0, 0.0, []),
            ("RB1", "carry", -3.0, 0.0, []),
            ("WR1", "route", -12.0, 0.0, [Waypoint(0.0, -12.0, 0.0), Waypoint(1.0, -4.0, 8.0)]),
            ("WR2", "route", 8.0, 0.0, [Waypoint(0.0, 8.0, 0.0), Waypoint(1.2, 12.0, 6.0)]),
            ("WR3", "route", 18.0, 0.0, [Waypoint(0.0, 18.0, 0.0), Waypoint(1.5, 10.0, 4.0)]),
            ("TE1", "route", 4.5, 0.0, [Waypoint(0.0, 4.5, 0.0), Waypoint(1.6, 4.5, 5.0)]),
            ("LT", "block", -6.0, 0.0, []),
            ("LG", "block", -3.5, 0.0, []),
            ("C", "block", 0.0, 0.0, []),
            ("RG", "block", 3.5, 0.0, []),
            ("RT", "block", 6.0, 0.0, []),
        ]
        for player_id, role, x, y, route in defaults:
            self._create_player(player_id, role, x, y, route)
        self.metadata_widget.set_metadata(
            {
                "play_id": "slant_flat_right",
                "name": "Slant Flat Right",
                "formation": "Trips Right",
                "personnel": "11",
                "play_type": "offense",
            }
        )
        self._current_path = None
        if self._player_order:
            self._items[self._player_order[0]].setSelected(True)

    def open_play(self) -> None:
        base_dir = Path("data/plays").resolve()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open Play",
            str(base_dir),
            "Play Files (*.json)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            play = Play.model_validate(data)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            QMessageBox.critical(self, "Open Play", f"Failed to load play: {exc}")
            return

        self._clear_players()
        self.metadata_widget.set_metadata(
            {
                "play_id": play.play_id,
                "name": play.name,
                "formation": play.formation,
                "personnel": play.personnel,
                "play_type": play.play_type,
            }
        )
        for assignment in play.assignments:
            route = [
                Waypoint(pt.timestamp, pt.x, pt.y)
                for pt in assignment.route
            ] if assignment.route else []
            anchor_x, anchor_y = (route[0].x, route[0].y) if route else (0.0, 0.0)
            self._create_player(assignment.player_id, assignment.role, anchor_x, anchor_y, route)
        self._current_path = path
        if self._player_order:
            self._items[self._player_order[0]].setSelected(True)

    def save_play(self) -> None:
        if not self._current_path:
            self.save_play_as()
            return
        self._save_to_path(self._current_path)

    def save_play_as(self) -> None:
        base_dir = Path("data/plays").resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Play As",
            str(base_dir),
            "Play Files (*.json)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        self._save_to_path(path)
        self._current_path = path

    def _save_to_path(self, path: Path) -> None:
        if not self.validate_current_play(show_dialog=False):
            return
        try:
            data = self.serialize_play()
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "Save Play", f"Failed to save play: {exc}")

    def mirror_play(self) -> None:
        self._suspend_token_updates = True
        try:
            for player_id in self._player_order:
                state = self._states[player_id]
                state.anchor_x = -state.anchor_x
                if state.waypoints:
                    for waypoint in state.waypoints:
                        waypoint.x = -waypoint.x
                item = self._items[player_id]
                item.setPos(self.geometry.field_to_scene(state.anchor_x, state.anchor_y))
        finally:
            self._suspend_token_updates = False
        self.player_panel.set_state(None)

    def closeEvent(self, event):  # type: ignore[override]
        self.scene.clearSelection()
        super().closeEvent(event)


def main() -> None:
    app = QApplication([])
    editor = PlayEditor()
    editor.resize(1100, 720)
    editor.show()
    app.exec()


if __name__ == "__main__":
    main()
