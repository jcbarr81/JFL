from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import Iterator

from sqlalchemy import Column, JSON, Enum as SAEnum, String
from sqlmodel import Field, Session, SQLModel, create_engine

DATABASE_URL = "sqlite:///gridiron.db"
engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


class PositionEnum(str, Enum):
    """Enumeration of valid football positions for persistence."""

    QB = "QB"
    RB = "RB"
    WR = "WR"
    TE = "TE"
    OL = "OL"
    DL = "DL"
    LB = "LB"
    CB = "CB"
    S = "S"
    K = "K"
    P = "P"


POSITION_COLUMN = SAEnum(PositionEnum, name="football_position")


class PlayerRow(SQLModel, table=True):
    """ORM representation of players stored in the database."""

    player_id: str = Field(primary_key=True, description="External player identifier")
    name: str = Field(index=True)
    position: PositionEnum = Field(sa_column=Column(POSITION_COLUMN))
    jersey_number: int = Field(ge=0, le=99)
    team_id: str | None = Field(default=None, foreign_key="teamrow.team_id")
    attributes: dict[str, int] | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Serialized attribute ratings",
    )


class TeamRow(SQLModel, table=True):
    """ORM representation of a franchise/team."""

    team_id: str = Field(primary_key=True)
    name: str
    city: str
    abbreviation: str = Field(
        sa_column=Column(String(length=4), unique=True, nullable=False),
        min_length=2,
        max_length=4,
    )


class SeasonRow(SQLModel, table=True):
    """Season metadata for league play."""

    season_id: str = Field(primary_key=True)
    year: int = Field(ge=1900, le=2100)
    description: str | None = None
    is_current: bool = Field(default=False)


class GameRow(SQLModel, table=True):
    """Individual scheduled or completed games."""

    game_id: str = Field(primary_key=True)
    season_id: str | None = Field(default=None, foreign_key="seasonrow.season_id")
    week: int = Field(ge=1, le=25)
    home_team_id: str = Field(foreign_key="teamrow.team_id")
    away_team_id: str = Field(foreign_key="teamrow.team_id")
    scheduled_at: datetime | None = Field(default=None)
    played: bool = Field(default=False)


class BoxScoreRow(SQLModel, table=True):
    """Per-game statistics for teams and players."""

    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(foreign_key="gamerow.game_id")
    team_id: str = Field(foreign_key="teamrow.team_id")
    player_id: str | None = Field(default=None, foreign_key="playerrow.player_id")
    stat_type: str = Field(description="Statistic category identifier")
    stat_payload: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Arbitrary stat payload",
    )


class EventRow(SQLModel, table=True):
    """Log of discrete events occurring within a game."""

    id: int | None = Field(default=None, primary_key=True)
    game_id: str = Field(foreign_key="gamerow.game_id")
    occurred_at: datetime = Field(default_factory=datetime.utcnow)
    event_type: str = Field(description="Event type label")
    description: str | None = None
    event_metadata: dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
        description="Structured event metadata",
    )


class DraftProspectRow(SQLModel, table=True):
    """Draft prospect information prior to league entry."""

    prospect_id: str = Field(primary_key=True)
    name: str
    position: PositionEnum = Field(sa_column=Column(POSITION_COLUMN))
    college: str | None = None
    projected_round: int | None = Field(default=None, ge=1, le=7)
    scouting_report: str | None = None


def create_all() -> None:
    """Create all SQLModel tables in the configured SQLite database."""

    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a transactional session bound to the configured engine."""

    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
