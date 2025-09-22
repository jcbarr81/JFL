from __future__ import annotations

from typing import Callable, Iterable

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QTableView,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class _StyledMixin:
    """Utility mixin to refresh style after changing Qt properties."""

    def _refresh_style(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class PrimaryButton(QPushButton, _StyledMixin):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("variant", "primary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_style()


class SecondaryButton(QPushButton, _StyledMixin):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("variant", "secondary")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_style()


class IconButton(QToolButton, _StyledMixin):
    def __init__(self, icon: QIcon | None = None, tooltip: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", "icon")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon is not None:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip(tooltip)
        self._refresh_style()


class Card(QFrame, _StyledMixin):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("component", "card")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._refresh_style()


class ClickableCard(Card):
    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class Tag(QLabel, _StyledMixin):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("component", "tag")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_style()


class ValuePill(QLabel, _StyledMixin):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setProperty("component", "pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_style()


class StatePlaceholder(QFrame, _StyledMixin):
    """Branded placeholder that communicates loading, empty, or error state."""

    def __init__(
        self,
        title: str,
        description: str | None = None,
        variant: str = "empty",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("component", "state-placeholder")
        self._title = QLabel(title, self)
        self._title.setObjectName("state-placeholder-title")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description = QLabel(description or "", self)
        self._description.setObjectName("state-placeholder-description")
        self._description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._description.setWordWrap(True)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(180)
        self._progress.setTextVisible(False)
        self._action_button: SecondaryButton | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)
        layout.addWidget(self._description)
        layout.addWidget(self._progress)

        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        self.setProperty("state", variant)
        self._progress.setVisible(variant == "loading")
        self._refresh_style()

    def set_title(self, title: str) -> None:
        self._title.setText(title)

    def set_description(self, description: str | None) -> None:
        self._description.setText(description or "")

    def set_action(self, label: str, handler: Callable[[], None]) -> None:
        if self._action_button is None:
            self._action_button = SecondaryButton(label, self)
            self.layout().addWidget(self._action_button)
        else:
            self._action_button.setText(label)
        try:
            self._action_button.clicked.disconnect()  # type: ignore[call-arg]
        except TypeError:
            pass
        self._action_button.clicked.connect(handler)  # type: ignore[arg-type]
        self._action_button.show()

    def clear_action(self) -> None:
        if self._action_button is not None:
            self._action_button.hide()
            try:
                self._action_button.clicked.disconnect()  # type: ignore[call-arg]
            except TypeError:
                pass


class BusyOverlay(QFrame, _StyledMixin):
    """Semi-transparent overlay with spinner to block interaction during work."""

    def __init__(self, parent: QWidget, message: str = "Working...") -> None:
        super().__init__(parent)
        self.setProperty("component", "busy-overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint)
        self.setVisible(False)
        parent.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        self._progress = QProgressBar(self)
        self._progress.setRange(0, 0)
        self._progress.setFixedWidth(220)
        self._progress.setTextVisible(False)
        self._label = QLabel(message, self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._progress)
        layout.addWidget(self._label)
        self._refresh_style()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj is self.parent():
            if event.type() in {QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show}:
                self._sync_geometry()
        return super().eventFilter(obj, event)

    def show_message(self, message: str | None = None) -> None:
        if message:
            self._label.setText(message)
        self._sync_geometry()
        self.show()
        self.raise_()

    def hide_overlay(self) -> None:
        self.hide()

    def _sync_geometry(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())


class DataTable(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)


class FormRow(QWidget):
    def __init__(self, label: str, field: QWidget, hint: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label_widget = QLabel(label)
        label_widget.setObjectName("form-row-label")
        layout.addWidget(label_widget)
        layout.addWidget(field)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("form-row-hint")
            hint_label.setProperty("component", "tag")
            layout.addWidget(hint_label)


class Modal(QDialog):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)
        self._body = QTextEdit()
        self._body.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_content(self, text: str) -> None:
        self._body.setPlainText(text)


class ConfirmDialog(QMessageBox):
    """Utility confirmation dialog with consistent button ordering."""

    @staticmethod
    def ask(
        parent: QWidget,
        title: str,
        message: str,
        *,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
    ) -> bool:
        dialog = ConfirmDialog(parent)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        ok_button = dialog.button(QMessageBox.StandardButton.Ok)
        cancel_button = dialog.button(QMessageBox.StandardButton.Cancel)
        if ok_button is not None:
            ok_button.setText(confirm_label)
        if cancel_button is not None:
            cancel_button.setText(cancel_label)
        dialog.setDefaultButton(QMessageBox.StandardButton.Ok)
        return dialog.exec() == QMessageBox.StandardButton.Ok


class Toast(QFrame):
    def __init__(self, message: str, duration_ms: int = 3000, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setProperty("component", "card")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        label = QLabel(message, self)
        layout.addWidget(label)
        self._duration_ms = duration_ms
        self._animation = QPropertyAnimation(self, b"pos")
        self._animation.setDuration(250)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_at_parent(self, parent: QWidget) -> None:
        if parent.window() is not None:
            parent = parent.window()
        geom: QRect = parent.geometry()
        self.adjustSize()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + geom.height() - self.height() - 32
        start = QPoint(x, y + 20)
        end = QPoint(x, y)
        self.move(start)
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.start()
        QTimer.singleShot(self._duration_ms, self.close)

    @staticmethod
    def show_message(parent: QWidget, message: str, duration_ms: int = 3000) -> None:
        toast = Toast(message, duration_ms, parent)
        toast.show_at_parent(parent)


def apply_form_layout_spacing(rows: Iterable[FormRow]) -> None:
    for row in rows:
        row.layout().setSpacing(6)  # type: ignore[union-attr]
