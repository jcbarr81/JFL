from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session

from domain.db import get_session


def db_session() -> Iterator[Session]:
    with get_session() as session:
        yield session
