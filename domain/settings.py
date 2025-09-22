from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from domain.db import AppSettingRow, engine

LOGGER = logging.getLogger("domain.settings")


def get_setting(key: str) -> Optional[str]:
    """Return the stored value for *key* or ``None`` if not present/accessible."""

    try:
        with Session(engine) as session:
            row = session.get(AppSettingRow, key)
            return row.value if row else None
    except SQLAlchemyError as exc:  # pragma: no cover - defensive
        LOGGER.warning("Unable to read setting '%s': %s", key, exc)
        return None


def set_setting(key: str, value: str) -> bool:
    """Persist *value* for *key*. Returns ``True`` on success."""

    try:
        with Session(engine) as session:
            session.merge(AppSettingRow(key=key, value=value))
            session.commit()
        return True
    except SQLAlchemyError as exc:  # pragma: no cover - defensive
        LOGGER.warning("Unable to write setting '%s': %s", key, exc)
        return False
