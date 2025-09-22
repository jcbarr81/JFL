from __future__ import annotations

import base64
import json
import zlib
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

try:
    import orjson
except ImportError:  # pragma: no cover - optional dependency
    orjson = None
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import db_session
from domain.db import BoxScoreRow, GameRow, PlayerRow, TeamRow
from domain.gameplan import GameplanRepository
from domain.models import Attributes, Player
from sim.ruleset import GameConfig, GameSummary, simulate_game
from sim.statbook import StatBook

DEFAULT_USER_HOME = Path.home() / "GridironSim"

router = APIRouter(prefix="/game", tags=["game"])


class GameConfigPayload(BaseModel):
    quarter_length: float | None = Field(default=None, ge=60.0, le=900.0)
    quarters: int | None = Field(default=None, ge=1, le=6)
    max_plays: int | None = Field(default=None, ge=10, le=200)
    kickoff_yardline: float | None = Field(default=None, ge=0.0, le=35.0)


class GameSimulationRequest(BaseModel):
    home_team_id: str
    away_team_id: str
    seed: int = Field(default=0, description="Random seed for the simulation")
    week: int = Field(default=1, ge=1, le=25)
    season_id: str | None = None
    save: bool = Field(default=True, description="Persist the result to the database")
    config: GameConfigPayload | None = None


class DriveSummaryPayload(BaseModel):
    offense: str
    quarter: int
    plays: int
    yards: float
    duration: float
    start_yardline: float
    end_yardline: float
    result: str


class GameSimulationResponse(BaseModel):
    game_id: str | None
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    winner: str | None
    total_plays: int
    drives: list[DriveSummaryPayload]
    boxscore: Dict[str, Any]
    events_blob: str | None = None
    gameplan_results: Dict[str, Any] | None = None


def _encode_events(summary: GameSummary) -> str | None:
    if not summary.home_events and not summary.away_events:
        return None
    payload = {
        "home": [asdict(evt) for evt in summary.home_events],
        "away": [asdict(evt) for evt in summary.away_events],
    }
    if orjson is not None:
        raw = orjson.dumps(payload)
    else:
        raw = json.dumps(payload).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return base64.b64encode(compressed).decode("ascii")


def _attributes_from_payload(payload: dict[str, int] | None) -> Attributes:
    base = {
        "speed": 60,
        "strength": 60,
        "agility": 60,
        "awareness": 60,
        "catching": 60,
        "tackling": 60,
        "throwing_power": 60,
        "accuracy": 60,
    }
    if payload:
        base.update({key: int(value) for key, value in payload.items()})
    return Attributes(**base)


def _roster(session: Session, team_id: str) -> Dict[str, Player]:
    team = session.get(TeamRow, team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found")
    players = session.exec(select(PlayerRow).where(PlayerRow.team_id == team_id)).all()
    if not players:
        raise HTTPException(status_code=400, detail=f"Team '{team_id}' has no players")
    roster: Dict[str, Player] = {}
    for row in players:
        attrs = _attributes_from_payload(row.attributes or {})
        roster[row.player_id] = Player(
            player_id=row.player_id,
            name=row.name,
            position=row.position.value,
            jersey_number=row.jersey_number,
            attributes=attrs,
            team_id=row.team_id,
        )
    return roster


def _build_config(payload: GameConfigPayload | None) -> GameConfig | None:
    if not payload:
        return None
    config_kwargs = {}
    if payload.quarter_length is not None:
        config_kwargs["quarter_length"] = payload.quarter_length
    if payload.quarters is not None:
        config_kwargs["quarters"] = payload.quarters
    if payload.max_plays is not None:
        config_kwargs["max_plays"] = payload.max_plays
    if payload.kickoff_yardline is not None:
        config_kwargs["kickoff_yardline"] = payload.kickoff_yardline
    return GameConfig(**config_kwargs) if config_kwargs else None


def _persist_game(
    session: Session,
    summary: GameSummary,
    request: GameSimulationRequest,
) -> str:
    game_id = f"GAME-{uuid4().hex[:12]}"
    session.add(
        GameRow(
            game_id=game_id,
            season_id=request.season_id,
            week=request.week,
            home_team_id=summary.home_team,
            away_team_id=summary.away_team,
            played=True,
        )
    )
    session.add(
        BoxScoreRow(
            game_id=game_id,
            team_id=summary.home_team,
            player_id=None,
            stat_type="team_game",
            stat_payload=summary.home_boxscore.get("teams", {}),
        )
    )
    for player_id, stats in summary.home_boxscore.get("players", {}).items():
        session.add(
            BoxScoreRow(
                game_id=game_id,
                team_id=summary.home_team,
                player_id=player_id,
                stat_type="player_game",
                stat_payload=stats,
            )
        )
    session.add(
        BoxScoreRow(
            game_id=game_id,
            team_id=summary.away_team,
            player_id=None,
            stat_type="team_game",
            stat_payload=summary.away_boxscore.get("teams", {}),
        )
    )
    for player_id, stats in summary.away_boxscore.get("players", {}).items():
        session.add(
            BoxScoreRow(
                game_id=game_id,
                team_id=summary.away_team,
                player_id=player_id,
                stat_type="player_game",
                stat_payload=stats,
            )
        )
    return game_id


@router.post("/simulate", response_model=GameSimulationResponse, status_code=status.HTTP_201_CREATED)
async def simulate_game_endpoint(
    payload: GameSimulationRequest,
    session: Session = Depends(db_session),
) -> GameSimulationResponse:
    if payload.home_team_id == payload.away_team_id:
        raise HTTPException(status_code=400, detail="Home and away teams must differ")

    home_roster = _roster(session, payload.home_team_id)
    away_roster = _roster(session, payload.away_team_id)

    config = _build_config(payload.config)
    home_book = StatBook()
    away_book = StatBook()


    repo = GameplanRepository(DEFAULT_USER_HOME)
    home_plan = repo.load_plan(payload.home_team_id, opponent_id=payload.away_team_id, week=payload.week)
    away_plan = repo.load_plan(payload.away_team_id, opponent_id=payload.home_team_id, week=payload.week)

    summary = await run_in_threadpool(
        simulate_game,
        payload.home_team_id,
        home_roster,
        home_book,
        payload.away_team_id,
        away_roster,
        away_book,
        seed=payload.seed,
        config=config,
        week=payload.week,
        home_plan=home_plan,
        away_plan=away_plan,
    )

    game_id: str | None = None
    if payload.save:
        game_id = _persist_game(session, summary, payload)
        session.commit()

    events_blob = _encode_events(summary)
    drives = [DriveSummaryPayload(**asdict(drive)) for drive in summary.drives]
    return GameSimulationResponse(
        game_id=game_id,
        home_team=summary.home_team,
        away_team=summary.away_team,
        home_score=summary.home_score,
        away_score=summary.away_score,
        winner=summary.winner,
        total_plays=summary.total_plays,
        drives=drives,
        boxscore={
            "home": summary.home_boxscore,
            "away": summary.away_boxscore,
        },
        events_blob=events_blob,
        gameplan_results=summary.gameplan_results if summary.gameplan_results else None,
    )
