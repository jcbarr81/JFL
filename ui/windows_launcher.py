from __future__ import annotations

import os
import shutil
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from random import randint
from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_season import OUTPUT_DIR, run_season
from sim.schedule import SeasonResult
from ui.play_editor.editor import PlayEditor

APP_DIR_NAME = "GridironSim"
DEFAULT_DB_NAME = "gridiron.db"
PLAY_REL_DIR = Path("data/plays")
ASSET_DIR_NAME = "assets"


@dataclass
class LauncherConfig:
    user_home: Path
    assets_root: Path


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _bundle_root() -> Path:
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return ROOT


def _asset_root() -> Path:
    root = _bundle_root()
    candidate = root / ASSET_DIR_NAME
    if candidate.exists():
        return candidate
    return ROOT


def _local_appdata() -> Path:
    raw = os.environ.get("LOCALAPPDATA")
    if raw:
        return Path(raw)
    # Fallback for non-Windows environments (dev)
    return Path.home() / "AppData" / "Local"


def _copy_file_if_missing(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _sync_tree_if_missing(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    for child in src.rglob("*"):
        relative = child.relative_to(src)
        target = dest / relative
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, target)


def prepare_environment() -> LauncherConfig:
    assets_root = _asset_root()
    user_home = _local_appdata() / APP_DIR_NAME
    user_home.mkdir(parents=True, exist_ok=True)

    db_src = assets_root / DEFAULT_DB_NAME
    db_dest = user_home / DEFAULT_DB_NAME
    _copy_file_if_missing(db_src, db_dest)

    plays_src = assets_root / PLAY_REL_DIR
    plays_dest = user_home / PLAY_REL_DIR
    _sync_tree_if_missing(plays_src, plays_dest)

    # Ensure expected directories exist for exports/savepoints
    (user_home / "data" / "savepoints").mkdir(parents=True, exist_ok=True)
    (user_home / "build").mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("GRIDIRON_HOME", str(user_home))
    os.chdir(user_home)
    return LauncherConfig(user_home=user_home, assets_root=assets_root)


class LauncherWindow(QMainWindow):
    def __init__(self, config: LauncherConfig) -> None:
        super().__init__()
        self.setWindowTitle("Gridiron Sim Launcher")
        self.resize(560, 360)
        self.config = config
        self._play_editor: Optional[PlayEditor] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._season_future: Optional[Future[SeasonResult]] = None

        self.status_label = QLabel("Ready")
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMinimumHeight(140)

        run_button = QPushButton("Run Season Simulation")
        run_button.clicked.connect(self.handle_run_season)  # type: ignore[arg-type]
        self.run_button = run_button

        editor_button = QPushButton("Open Play Editor")
        editor_button.clicked.connect(self.handle_open_editor)  # type: ignore[arg-type]

        open_data_button = QPushButton("Open Data Directory")
        open_data_button.clicked.connect(self.handle_open_data_dir)  # type: ignore[arg-type]

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"User data directory: {self.config.user_home}"))
        layout.addWidget(run_button)
        layout.addWidget(editor_button)
        layout.addWidget(open_data_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.output_log)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def handle_open_editor(self) -> None:
        if self._play_editor is None:
            self._play_editor = PlayEditor()
            self._play_editor.setWindowTitle("Gridiron Sim Play Editor")
        self._play_editor.show()
        self._play_editor.raise_()
        self._play_editor.activateWindow()

    def handle_open_data_dir(self) -> None:
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.config.user_home)  # type: ignore[attr-defined]
            else:
                QFileDialog.getOpenFileName(self, "Data Directory", str(self.config.user_home))
        except OSError as exc:
            QMessageBox.warning(self, "Open Directory", f"Unable to open folder: {exc}")

    def handle_run_season(self) -> None:
        if self._season_future and not self._season_future.done():
            QMessageBox.information(
                self,
                "Season Simulation",
                "A simulation is already running. Please wait.",
            )
            return

        seed = randint(0, 999999)
        self.status_label.setText(f"Simulating season (seed={seed})...")
        self.run_button.setEnabled(False)
        self.output_log.append("Starting season simulation...\n")

        def task() -> SeasonResult:
            return run_season(seed=seed)

        future = self._executor.submit(task)
        self._season_future = future
        future.add_done_callback(self._handle_season_finished)

    def _handle_season_finished(self, future: Future[SeasonResult]) -> None:
        def update_ui() -> None:
            self.run_button.setEnabled(True)
            if future.cancelled():
                self.status_label.setText("Simulation cancelled")
                return
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                self.status_label.setText("Simulation failed")
                QMessageBox.critical(self, "Season Simulation", f"Simulation failed: {exc}")
                self.output_log.append(f"Simulation failed: {exc}\n")
                return

            top_seed = result.standings[0] if result.standings else ("N/A", 0, 0)
            summary = (
                f"Season complete. Top seed: {top_seed[0]} ({top_seed[1]}-{top_seed[2]}).\n"
                f"Exports written to {OUTPUT_DIR.resolve()}"
            )
            self.status_label.setText("Season simulation finished")
            self.output_log.append(summary + "\n")
            QMessageBox.information(self, "Season Simulation", summary)

        QTimer.singleShot(0, update_ui)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def main() -> None:
    config = prepare_environment()
    app = QApplication(sys.argv)
    window = LauncherWindow(config)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
