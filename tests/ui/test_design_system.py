import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QStackedWidget, QWidget

from ui.core import (
    AppWindow,
    BusyOverlay,
    Card,
    EventBus,
    NavItem,
    PrimaryButton,
    SecondaryButton,
    StatePlaceholder,
    Tag,
    ThemeManager,
    ValuePill,
)
from ui.windows_launcher import FranchiseWindow, LauncherConfig


@pytest.fixture(scope="session")
def qt_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_manager_toggle(qt_app: QApplication) -> None:
    manager = ThemeManager()
    manager.attach(qt_app)
    assert qt_app.property("themeName") == "dark"
    manager.toggle()
    assert qt_app.property("themeName") == "light"


def test_component_properties(qt_app: QApplication) -> None:
    primary = PrimaryButton("Save")
    secondary = SecondaryButton("Cancel")
    tag = Tag("Status")
    pill = ValuePill("95")
    card = Card()

    assert primary.property("variant") == "primary"
    assert secondary.property("variant") == "secondary"
    assert tag.property("component") == "tag"
    assert pill.property("component") == "pill"
    assert card.property("component") == "card"


def test_state_placeholder_variants() -> None:
    placeholder = StatePlaceholder("Loading", "Please wait", variant="loading")
    assert placeholder.property("state") == "loading"
    placeholder.set_variant("error")
    assert placeholder.property("state") == "error"
    placeholder.set_title("Error")
    placeholder.set_description("Something went wrong")


def test_busy_overlay_tracks_parent_geometry(qt_app: QApplication) -> None:
    parent = QWidget()
    parent.resize(240, 120)
    overlay = BusyOverlay(parent, "Working...")
    parent.show()
    overlay.show_message()
    qt_app.processEvents()
    assert overlay.isVisible()
    assert overlay.geometry().size() == parent.geometry().size()
    overlay.hide_overlay()
    parent.close()


def test_app_window_navigation_updates_stack(qt_app: QApplication) -> None:
    manager = ThemeManager()
    manager.attach(qt_app)
    bus = EventBus()
    window = AppWindow(manager, bus)
    try:
        home = QWidget()
        team = QWidget()
        window.register_page(NavItem("home", "Home"), home)
        window.register_page(NavItem("team", "Team"), team)
        window.show()
        qt_app.processEvents()

        nav_buttons = window.findChildren(QPushButton, "nav-button")
        assert len(nav_buttons) == 2
        nav_buttons[1].click()
        qt_app.processEvents()

        stack = window.findChild(QStackedWidget)
        assert stack is not None
        assert stack.currentWidget() is team
        assert window.findChild(QLabel, "top-bar-title").text() == "Team"
    finally:
        window.close()


def test_nav_request_routes_to_page(qt_app: QApplication, tmp_path: Path) -> None:
    manager = ThemeManager()
    manager.attach(qt_app)
    bus = EventBus()
    config = LauncherConfig(
        user_home=tmp_path,
        assets_root=tmp_path,
        log_file=tmp_path / "launcher.log",
    )
    window = FranchiseWindow(config, manager, bus)
    try:
        window.show()
        qt_app.processEvents()
        bus.emit("nav.request", "gm")
        qt_app.processEvents()
        title = window.findChild(QLabel, "top-bar-title")
        assert title is not None
        assert title.text() == "Contracts & Salary Cap"
    finally:
        window.close()
