from __future__ import annotations

import logging
import os
import shutil
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from random import randint
from typing import Optional

LOGGER = logging.getLogger('gridiron.launcher')

from PyQt6.QtCore import QTimer, pyqtSignal
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
    log_file: Path


def _configure_logging(log_file: Path) -> None:
    LOGGER.handlers.clear()
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False



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
    log_file = user_home / "launcher.log"
    _configure_logging(log_file)
    LOGGER.info("Preparing environment (assets_root=%s)", assets_root)

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
    LOGGER.info("Environment ready; working directory set to %s", user_home)
    return LauncherConfig(user_home=user_home, assets_root=assets_root, log_file=log_file)


class LauncherWindow(QMainWindow):
    seasonFinished = pyqtSignal(object, object)

    def __init__(self, config: LauncherConfig) -> None:
        super().__init__()
        self.setWindowTitle("Gridiron Sim Launcher")
        self.resize(560, 360)
        self.config = config
        self.seasonFinished.connect(self._on_season_finished)
        self._play_editor: Optional[PlayEditor] = None
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._season_future: Optional[Future[SeasonResult]] = None

        self.status_label = QLabel("Ready")
        self.output_log = QTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMinimumHeight(140)
        self.log_file = config.log_file
        self.append_log(f"Log file: {self.log_file}")
        LOGGER.info("Launcher window initialized; log file at %s", self.log_file)

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

    def append_log(self, message: str) -> None:
        self.output_log.append(message)

    def handle_open_editor(self) -> None:
        LOGGER.info("Opening play editor window")
        if self._play_editor is None:
            self._play_editor = PlayEditor()
            self._play_editor.setWindowTitle("Gridiron Sim Play Editor")
        self._play_editor.show()
        self._play_editor.raise_()
        self._play_editor.activateWindow()
        self.append_log("Play editor opened")

    def handle_open_data_dir(self) -> None:
        LOGGER.info("Opening data directory at %s", self.config.user_home)
        try:
            if sys.platform.startswith("win"):
                os.startfile(self.config.user_home)  # type: ignore[attr-defined]
                self.append_log("Data directory opened in File Explorer")
            else:
                QFileDialog.getOpenFileName(self, "Data Directory", str(self.config.user_home))
                self.append_log("Data directory dialog opened")
        except OSError as exc:
            LOGGER.exception("Unable to open data directory")
            QMessageBox.warning(self, "Open Directory", f"Unable to open folder: {exc}")
            self.append_log(f"Failed to open data directory: {exc}")

    def handle_run_season(self) -> None:
        if self._season_future and not self._season_future.done():
            QMessageBox.information(
                self,
                "Season Simulation",
                "A simulation is already running. Please wait.",
            )
            return

        seed = randint(0, 999999)
        LOGGER.info("Starting season simulation (seed=%s)", seed)
        self.status_label.setText(f"Simulating season (seed={seed})...")
        self.run_button.setEnabled(False)
        self.append_log(f"Starting season simulation (seed={seed})")

        def task() -> SeasonResult:
            LOGGER.info("Season simulation worker thread started")
            try:
                result = run_season(seed=seed, workers=1)
                LOGGER.info("Season simulation worker thread completed")
                return result
            except Exception:
                LOGGER.exception("Season simulation worker thread raised an exception")
                raise

        future = self._executor.submit(task)
        self._season_future = future
        future.add_done_callback(self._handle_season_finished)

    def _handle_season_finished(self, future: Future[SeasonResult]) -> None:
        LOGGER.info("Season simulation future done callback executed (done=%s, cancelled=%s)", future.done(), future.cancelled())
        try:
            result = future.result()
            error: Exception | None = None
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            result = None
            error = exc
        self.seasonFinished.emit(result, error)

    def _on_season_finished(self, result: SeasonResult | None, error: Exception | None) -> None:
        LOGGER.info("Season simulation UI update running")
        self.run_button.setEnabled(True)
        self._season_future = None
        if error is not None:
            LOGGER.exception("Season simulation failed", exc_info=error)
            self.status_label.setText("Simulation failed")
            QMessageBox.critical(self, "Season Simulation", f"Simulation failed: {error}")
            self.append_log(f"Simulation failed: {error}")
            return
        if result is None:
            LOGGER.warning("Season simulation returned no result")
            self.status_label.setText("Simulation failed")
            self.append_log("Simulation failed: no result returned")
            return
        top_seed = result.standings[0] if result.standings else ("N/A", 0, 0)
        summary = (
            f"Season complete. Top seed: {top_seed[0]} ({top_seed[1]}-{top_seed[2]}).\n"
            f"Exports written to {OUTPUT_DIR.resolve()}"
        )
        LOGGER.info("Season simulation finished; top seed %s (%s-%s)", top_seed[0], top_seed[1], top_seed[2])
        self.status_label.setText("Season simulation finished")
        self.append_log(summary)
        QMessageBox.information(self, "Season Simulation", summary)
        LOGGER.info("Season simulation notification displayed")

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
