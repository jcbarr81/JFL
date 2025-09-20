from __future__ import annotations

from collections import defaultdict
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import db_session
from domain.db import BoxScoreRow

router = APIRouter(prefix="/stats", tags=["stats"])


class TeamStatsResponse(BaseModel):
    team_id: str
    games: int
    totals: Dict[str, Dict[str, float]]
    per_game: Dict[str, Dict[str, float]]


class PlayerStatsResponse(BaseModel):
    player_id: str
    team_ids: list[str]
    games: int
    totals: Dict[str, float]
    per_game: Dict[str, float]


def _aggregate_nested(rows: list[BoxScoreRow]) -> Dict[str, Dict[str, float]]:
    totals: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        payload = row.stat_payload or {}
        for phase, stats in payload.items():
            if not isinstance(stats, dict):
                continue
            phase_bucket = totals[phase]
            for key, value in stats.items():
                phase_bucket[key] += float(value)
    return {phase: dict(stats) for phase, stats in totals.items()}


@router.get("/team/{team_id}", response_model=TeamStatsResponse)
async def team_stats(team_id: str, session: Session = Depends(db_session)) -> TeamStatsResponse:
    rows = session.exec(
        select(BoxScoreRow).where(BoxScoreRow.team_id == team_id, BoxScoreRow.player_id.is_(None))
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No stats found for team '{team_id}'")
    totals = _aggregate_nested(rows)
    games = len(rows)
    per_game = {
        phase: {key: value / games for key, value in stats.items()}
        for phase, stats in totals.items()
    }
    return TeamStatsResponse(team_id=team_id, games=games, totals=totals, per_game=per_game)


@router.get("/player/{player_id}", response_model=PlayerStatsResponse)
async def player_stats(player_id: str, session: Session = Depends(db_session)) -> PlayerStatsResponse:
    rows = session.exec(
        select(BoxScoreRow).where(BoxScoreRow.player_id == player_id)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No stats found for player '{player_id}'")
    totals: Dict[str, float] = defaultdict(float)
    team_ids: set[str] = set()
    for row in rows:
        team_ids.add(row.team_id)
        payload = row.stat_payload or {}
        for key, value in payload.items():
            if isinstance(value, (int, float)):
                totals[key] += float(value)
    games = len(rows)
    per_game = {key: value / games for key, value in totals.items()}
    return PlayerStatsResponse(
        player_id=player_id,
        team_ids=sorted(team_ids),
        games=games,
        totals=dict(totals),
        per_game=per_game,
    )
