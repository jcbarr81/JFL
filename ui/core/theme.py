from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemePalette:
    """Defines the core color tokens for the UI."""

    name: str
    mode: str  # "dark" or "light"
    background: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_muted: str
    primary: str
    primary_text: str
    secondary: str
    secondary_text: str
    accent: str
    success: str
    warning: str
    danger: str


DARK_THEME = ThemePalette(
    name="dark",
    mode="dark",
    background="#121417",
    surface="#1C1F24",
    surface_alt="#21252B",
    border="#2E3238",
    text="#F5F7FA",
    text_muted="#A3ADB8",
    primary="#3B82F6",
    primary_text="#F5F7FA",
    secondary="#2D323B",
    secondary_text="#F5F7FA",
    accent="#22D3EE",
    success="#16A34A",
    warning="#F59E0B",
    danger="#F87171",
)

LIGHT_THEME = ThemePalette(
    name="light",
    mode="light",
    background="#F5F7FA",
    surface="#FFFFFF",
    surface_alt="#EFF2F7",
    border="#D0D6E1",
    text="#1F2933",
    text_muted="#5F6B7A",
    primary="#2563EB",
    primary_text="#FFFFFF",
    secondary="#E2E8F0",
    secondary_text="#1F2933",
    accent="#0891B2",
    success="#047857",
    warning="#C2410C",
    danger="#DC2626",
)


class ThemeManager(QObject):
    """Central authority for applying and toggling the UI theme."""

    themeChanged = pyqtSignal(object)

    def __init__(self, default_palette: ThemePalette | None = None) -> None:
        super().__init__()
        self._palettes: Dict[str, ThemePalette] = {
            DARK_THEME.name: DARK_THEME,
            LIGHT_THEME.name: LIGHT_THEME,
        }
        self._current = default_palette or DARK_THEME
        self._app: QApplication | None = None

    @property
    def current(self) -> ThemePalette:
        return self._current

    def palettes(self) -> Iterable[ThemePalette]:
        return self._palettes.values()

    def register_palette(self, palette: ThemePalette) -> None:
        self._palettes[palette.name] = palette

    def attach(self, app: QApplication) -> None:
        """Bind to a QApplication and immediately apply the active palette."""
        self._app = app
        self._apply_to_app()

    def set_palette(self, name: str) -> None:
        palette = self._palettes.get(name)
        if palette is None:
            raise KeyError(f"Unknown theme palette '{name}'")
        self._set_palette(palette)

    def toggle(self) -> None:
        next_palette = LIGHT_THEME if self._current.mode == "dark" else DARK_THEME
        self._set_palette(next_palette)

    def _set_palette(self, palette: ThemePalette) -> None:
        if palette == self._current:
            return
        self._current = palette
        self._apply_to_app()
        self.themeChanged.emit(palette)

    def _apply_to_app(self) -> None:
        if self._app is None:
            return
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(self._current.background))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(self._current.text))
        palette.setColor(QPalette.ColorRole.Base, QColor(self._current.surface))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(self._current.surface_alt))
        palette.setColor(QPalette.ColorRole.Text, QColor(self._current.text))
        palette.setColor(QPalette.ColorRole.Button, QColor(self._current.surface))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(self._current.text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(self._current.primary))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(self._current.primary_text))
        self._app.setPalette(palette)
        self._app.setStyleSheet(self._build_stylesheet(self._current))
        self._app.setProperty("themeName", self._current.name)

    def _build_stylesheet(self, palette: ThemePalette) -> str:
        """Generate the application-wide stylesheet from core tokens."""
        return f"""
        QWidget {{
            background-color: {palette.background};
            color: {palette.text};
            font-family: 'Segoe UI', 'Roboto', sans-serif;
            font-size: 14px;
        }}

        QFrame#nav-sidebar {{
            background-color: {palette.surface};
            border-right: 1px solid {palette.border};
        }}

        QPushButton#nav-button {{
            background-color: transparent;
            color: {palette.text_muted};
            border: none;
            text-align: left;
            padding: 12px 14px;
            border-radius: 10px;
        }}
        QPushButton#nav-button:hover {{
            background-color: {palette.surface_alt};
            color: {palette.text};
        }}
        QPushButton#nav-button:checked {{
            background-color: {palette.primary}22;
            color: {palette.text};
        }}

        QFrame#top-bar {{
            background-color: {palette.surface};
            border-bottom: 1px solid {palette.border};
        }}
        QLabel#top-bar-title {{
            font-weight: 700;
            font-size: 20px;
        }}
        QPushButton#top-bar-team {{
            background-color: {palette.secondary};
            color: {palette.secondary_text};
            border: 1px solid {palette.border};
            border-radius: 8px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QPushButton#top-bar-team:hover {{
            background-color: {palette.surface_alt};
        }}


        QFrame[component='card'] {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 12px;
            padding: 12px;
        }}

        QLabel[component='tag'] {{
            background-color: {palette.surface_alt};
            border-radius: 8px;
            padding: 4px 8px;
            color: {palette.text_muted};
        }}

        QLabel[component='pill'] {{
            background-color: {palette.accent};
            border-radius: 999px;
            padding: 4px 12px;
            color: {palette.text};
            font-weight: 600;
        }}

        QFrame[component='state-placeholder'] {{
            background-color: {palette.surface_alt};
            border: 1px dashed {palette.border};
            border-radius: 12px;
            padding: 24px;
        }}

        QFrame[component='state-placeholder'][state='error'] {{
            border-color: {palette.danger};
        }}

        QFrame[component='state-placeholder'][state='loading'] {{
            border-style: solid;
            border-color: {palette.primary}66;
        }}

        QFrame[component='state-placeholder'][state='empty'] {{
            border-style: dashed;
        }}

        QLabel#state-placeholder-title {{
            font-weight: 600;
            font-size: 16px;
        }}

        QLabel#state-placeholder-description {{
            color: {palette.text_muted};
        }}

        QLabel#dashboard-tile-title {{
            font-weight: 600;
            font-size: 16px;
        }}

        QLabel#dashboard-tile-summary {{
            font-size: 22px;
            font-weight: 600;
        }}

        QLabel[role='tile-detail'] {{
            color: {palette.text_muted};
        }}

        QLabel#coach-roster-validation {{
            font-weight: 600;
        }}

        QLabel#coach-roster-title {{
            font-size: 18px;
            font-weight: 600;
        }}

        QFrame[component='busy-overlay'] {{
            background-color: {palette.background}CC;
        }}

        QFrame[component='busy-overlay'] QLabel {{
            color: {palette.text};
            font-weight: 600;
        }}

        QProgressBar {{
            border: 1px solid {palette.border};
            border-radius: 8px;
            background-color: {palette.surface};
            height: 10px;
        }}

        QProgressBar::chunk {{
            border-radius: 8px;
            background-color: {palette.primary};
        }}

        QPushButton[variant='primary'] {{
            background-color: {palette.primary};
            color: {palette.primary_text};
            border: none;
            border-radius: 8px;
            padding: 8px 16px;
            font-weight: 600;
        }}
        QPushButton[variant='primary']:hover {{
            background-color: {palette.primary}CC;
        }}
        QPushButton[variant='primary']:pressed {{
            background-color: {palette.primary}AA;
        }}
        QPushButton[variant='primary']:disabled {{
            background-color: {palette.primary}55;
            color: {palette.primary_text}AA;
        }}

        QPushButton[variant='secondary'] {{
            background-color: {palette.secondary};
            color: {palette.secondary_text};
            border: 1px solid {palette.border};
            border-radius: 8px;
            padding: 8px 16px;
        }}
        QPushButton[variant='secondary']:hover {{
            background-color: {palette.surface_alt};
        }}

        QToolButton[variant='icon'] {{
            background-color: transparent;
            border: none;
            padding: 6px;
            border-radius: 6px;
        }}
        QToolButton[variant='icon']:hover {{
            background-color: {palette.surface_alt};
        }}

        QHeaderView::section {{
            background-color: {palette.surface_alt};
            color: {palette.text_muted};
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid {palette.border};
        }}

        QTableView {{
            gridline-color: {palette.border};
            background-color: {palette.surface};
            alternate-background-color: {palette.surface_alt};
            selection-background-color: {palette.primary}33;
            selection-color: {palette.text};
        }}

        QLineEdit, QComboBox, QTextEdit {{
            background-color: {palette.surface};
            border: 1px solid {palette.border};
            border-radius: 8px;
            padding: 6px 10px;
        }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{
            border: 1px solid {palette.primary};
        }}

        QDialog {{
            background-color: {palette.surface};
        }}

        QMessageBox {{
            background-color: {palette.surface};
        }}
        """






