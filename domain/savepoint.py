from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

DEFAULT_DB_PATH = Path("gridiron.db")
DEFAULT_SAVE_DIR = Path("data/savepoints")
DEFAULT_PLAYS_DIR = Path("data/plays")


def create_savepoint(
    name: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    plays_path: Path | None = DEFAULT_PLAYS_DIR,
    extra_paths: Iterable[Path] | None = None,
    save_dir: Path = DEFAULT_SAVE_DIR,
) -> Path:
    """Persist the current database (and optional assets) under a named savepoint."""

    target = save_dir / name
    target.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")
    shutil.copy2(db_path, target / db_path.name)

    copied = []
    if plays_path and plays_path.exists():
        destination = target / plays_path.name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(plays_path, destination)
        copied.append(str(plays_path.name))

    for extra in extra_paths or []:
        if not extra.exists():
            continue
        destination = target / extra.name
        if extra.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(extra, destination)
        else:
            shutil.copy2(extra, destination)
        copied.append(extra.name)

    metadata = {
        "name": name,
        "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "db_file": db_path.name,
        "copied_assets": copied,
    }
    (target / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return target


def load_savepoint(
    name: str,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    plays_path: Path | None = DEFAULT_PLAYS_DIR,
    save_dir: Path = DEFAULT_SAVE_DIR,
) -> None:
    """Restore the database (and optional assets) from a named savepoint."""

    source = save_dir / name
    if not source.exists():
        raise FileNotFoundError(f"Savepoint '{name}' not found in {save_dir}")

    db_file = next((child for child in source.iterdir() if child.name == db_path.name), None)
    if not db_file:
        raise FileNotFoundError(f"Savepoint '{name}' missing database snapshot {db_path.name}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_file, db_path)

    plays_snapshot = source / (plays_path.name if plays_path else "") if plays_path else None
    if plays_path and plays_snapshot and plays_snapshot.exists():
        if plays_path.exists():
            shutil.rmtree(plays_path)
        shutil.copytree(plays_snapshot, plays_path)

