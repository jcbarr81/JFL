from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, TYPE_CHECKING

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .components import IconButton, PrimaryButton, SecondaryButton
from .events import EventBus
from .theme import ThemeManager

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ui.team.store import TeamInfo, TeamStore


@dataclass
class NavItem:
    key: str
    title: str
    icon: QIcon | None = None


class NavSidebar(QFrame):
    navigateRequested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nav-sidebar")
        self.setFixedWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(8)
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._buttons: Dict[str, QPushButton] = {}

    def add_item(self, item: NavItem) -> None:
        button = SecondaryButton(item.title, self)
        button.setCheckable(True)
        button.setObjectName("nav-button")
        if item.icon is not None:
            button.setIcon(item.icon)
            button.setIconSize(QSize(18, 18))
        self._button_group.addButton(button)
        self._buttons[item.key] = button
        button.clicked.connect(lambda _: self.navigateRequested.emit(item.key))  # type: ignore[arg-type]
        self.layout().addWidget(button)
        if len(self._buttons) == 1:
            button.setChecked(True)

    def set_active(self, key: str) -> None:
        button = self._buttons.get(key)
        if button:
            button.setChecked(True)


class TopBar(QFrame):
    requestSearch = pyqtSignal()

    def __init__(
        self,
        theme_manager: ThemeManager,
        event_bus: EventBus,
        parent: QWidget | None = None,
        *,
        team_store: "TeamStore" | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("top-bar")
        self._theme_manager = theme_manager
        self._event_bus = event_bus
        self._team_store: "TeamStore | None" = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(16)

        self._title_label = QLabel("Dashboard")
        self._title_label.setObjectName("top-bar-title")
        layout.addWidget(self._title_label)

        self._team_button = SecondaryButton("Select Team", self)
        self._team_button.setObjectName("top-bar-team")
        self._team_button.clicked.connect(self._handle_team_select)  # type: ignore[arg-type]
        layout.addWidget(self._team_button)

        layout.addStretch(1)

        self._save_button = PrimaryButton("Save", self)
        self._save_button.clicked.connect(lambda: self._event_bus.emit("shortcut.save"))
        layout.addWidget(self._save_button)

        self._search_button = SecondaryButton("Search", self)
        self._search_button.clicked.connect(self._on_search_clicked)
        layout.addWidget(self._search_button)

        self._theme_toggle = IconButton(parent=self)
        self._theme_toggle.setText("Theme")
        self._theme_toggle.setToolTip("Toggle theme")
        self._theme_toggle.clicked.connect(self._theme_manager.toggle)
        layout.addWidget(self._theme_toggle)

        if team_store is not None:
            self.bind_team_store(team_store)

    def bind_team_store(self, team_store: "TeamStore") -> None:
        if self._team_store is team_store:
            return
        if self._team_store is not None:
            try:
                self._team_store.teamChanged.disconnect(self._on_team_changed)
            except TypeError:  # pragma: no cover - defensive
                pass
        self._team_store = team_store
        team_store.teamChanged.connect(self._on_team_changed)
        self._on_team_changed(team_store.selected_team)

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def _handle_team_select(self) -> None:
        self._event_bus.emit("team.select.request")

    def _on_search_clicked(self) -> None:
        self.requestSearch.emit()
        self._event_bus.emit("shortcut.search")

    def _on_team_changed(self, team: "TeamInfo | None") -> None:
        if team is None:
            self._team_button.setText("Select Team")
            self._team_button.setToolTip("Choose a franchise")
        else:
            self._team_button.setText(team.abbreviation.upper())
            self._team_button.setToolTip(team.display_name)


class AppWindow(QMainWindow):
    def __init__(
        self,
        theme_manager: ThemeManager,
        event_bus: EventBus | None = None,
        *,
        team_store: "TeamStore" | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gridiron Franchise Studio")
        self.resize(1280, 800)
        self._theme_manager = theme_manager
        self._event_bus = event_bus or EventBus()
        self._pages: Dict[str, QWidget] = {}
        self._page_titles: Dict[str, str] = {}
        self._modals: set[QWidget] = set()

        container = QWidget(self)
        root_layout = QHBoxLayout(container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._sidebar = NavSidebar(container)
        self._sidebar.navigateRequested.connect(self._on_navigate_requested)
        root_layout.addWidget(self._sidebar)

        main_column = QWidget(container)
        main_layout = QVBoxLayout(main_column)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._topbar = TopBar(self._theme_manager, self._event_bus, main_column, team_store=team_store)
        self._topbar.requestSearch.connect(self._handle_search_requested)
        main_layout.addWidget(self._topbar)

        self._stack = QStackedWidget(main_column)
        main_layout.addWidget(self._stack)

        root_layout.addWidget(main_column)
        self.setCentralWidget(container)

        self._setup_shortcuts()

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    def register_page(self, item: NavItem, widget: QWidget, title: Optional[str] = None) -> None:
        if item.key in self._pages:
            raise KeyError(f"Page '{item.key}' already registered")
        self._pages[item.key] = widget
        self._page_titles[item.key] = title or item.title
        self._sidebar.add_item(item)
        self._stack.addWidget(widget)
        if self._stack.count() == 1:
            self._stack.setCurrentWidget(widget)
            self._topbar.set_title(self._page_titles[item.key])

    def _on_navigate_requested(self, key: str) -> None:
        widget = self._pages.get(key)
        if widget is None:
            return
        self._stack.setCurrentWidget(widget)
        self._topbar.set_title(self._page_titles.get(key, key.title()))
        self._sidebar.set_active(key)
        self._event_bus.emit("nav.changed", key)

    def _handle_search_requested(self) -> None:
        self._event_bus.emit("ui.search")

    def _setup_shortcuts(self) -> None:
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(lambda: self._event_bus.emit("shortcut.save"))
        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.activated.connect(lambda: self._event_bus.emit("shortcut.search"))
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self._close_active_modal)

    def register_modal(self, dialog: QWidget) -> None:
        self._modals.add(dialog)

        def _cleanup(_: object) -> None:
            self._modals.discard(dialog)

        dialog.destroyed.connect(_cleanup)  # type: ignore[arg-type]

    def _close_active_modal(self) -> None:
        for modal in list(self._modals):
            if modal.isVisible():
                modal.close()
                return
        self._event_bus.emit("shortcut.escape")
