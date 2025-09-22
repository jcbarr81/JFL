from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from domain.db import BoxScoreRow, GameRow, TeamRow, engine
from scripts.seed_league import TEAM_DEFINITIONS

LOGGER = logging.getLogger("domain.teams")


@dataclass(frozen=True)
class TeamInfo:
    team_id: str
    name: str
    city: str
    abbreviation: str

    @property
    def display_name(self) -> str:
        return f"{self.city} {self.name}".strip()


@dataclass(frozen=True)
class RecentGame:
    week: int
    opponent: str
    location: str
    played: bool


@dataclass
class TeamProfileData:
    team: TeamInfo
    games_played: int
    totals: Dict[str, Dict[str, float]]
    per_game: Dict[str, Dict[str, float]]
    recent_games: List[RecentGame]


def _aggregate_stats(rows: Iterable[BoxScoreRow]) -> tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]], int]:
    totals: Dict[str, Dict[str, float]] = {}
    games = 0
    for row in rows:
        games += 1
        payload = row.stat_payload or {}
        for phase, stats in payload.items():
            if not isinstance(stats, dict):
                continue
            bucket = totals.setdefault(phase, {})
            for key, value in stats.items():
                try:
                    bucket[key] = bucket.get(key, 0.0) + float(value)
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    continue
    per_game: Dict[str, Dict[str, float]] = {}
    if games:
        for phase, stats in totals.items():
            per_game[phase] = {metric: total / games for metric, total in stats.items()}
    return totals, per_game, games


class TeamRepository:
    """Data access helpers for team metadata and summaries."""

    def list_teams(self) -> List[TeamInfo]:
        try:
            with Session(engine) as session:
                rows = session.exec(select(TeamRow)).all()
            if rows:
                return [
                    TeamInfo(
                        team_id=row.team_id,
                        name=row.name,
                        city=row.city,
                        abbreviation=row.abbreviation,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load teams from database: %s", exc)
        return [
            TeamInfo(
                team_id=item["team_id"],
                name=item["name"],
                city=item["city"],
                abbreviation=item.get("abbreviation", item["team_id"]),
            )
            for item in TEAM_DEFINITIONS
        ]

    def _team_from_db(self, team_id: str) -> Optional[TeamInfo]:
        try:
            with Session(engine) as session:
                row = session.get(TeamRow, team_id)
            if row is None:
                return None
            return TeamInfo(
                team_id=row.team_id,
                name=row.name,
                city=row.city,
                abbreviation=row.abbreviation,
            )
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load team '%s': %s", team_id, exc)
            return None

    def find_team(self, team_id: str, *, fallbacks: bool = True) -> Optional[TeamInfo]:
        team = self._team_from_db(team_id)
        if team:
            return team
        if fallbacks:
            for item in TEAM_DEFINITIONS:
                if item["team_id"] == team_id:
                    return TeamInfo(
                        team_id=item["team_id"],
                        name=item["name"],
                        city=item["city"],
                        abbreviation=item.get("abbreviation", item["team_id"]),
                    )
        return None

    def load_profile(self, team_id: str) -> TeamProfileData:
        team = self.find_team(team_id)
        if team is None:
            raise ValueError(f"Unknown team '{team_id}'")
        try:
            with Session(engine) as session:
                rows = session.exec(
                    select(BoxScoreRow).where(
                        BoxScoreRow.team_id == team_id,
                        BoxScoreRow.player_id.is_(None),
                    )
                ).all()
                totals, per_game, games = _aggregate_stats(rows)
                recent_rows = session.exec(
                    select(GameRow)
                    .where((GameRow.home_team_id == team_id) | (GameRow.away_team_id == team_id))
                    .order_by(GameRow.week.desc())
                    .limit(5)
                ).all()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load profile for team '%s': %s", team_id, exc)
            return TeamProfileData(team=team, games_played=0, totals={}, per_game={}, recent_games=[])

        recent_games: List[RecentGame] = []
        for row in recent_rows:
            opponent: str
            location: str
            if row.home_team_id == team_id:
                opponent = row.away_team_id
                location = "Home"
            else:
                opponent = row.home_team_id
                location = "Away"
            recent_games.append(
                RecentGame(
                    week=row.week,
                    opponent=opponent,
                    location=location,
                    played=row.played,
                )
            )

        return TeamProfileData(
            team=team,
            games_played=games,
            totals=totals,
            per_game=per_game,
            recent_games=recent_games,
        )
