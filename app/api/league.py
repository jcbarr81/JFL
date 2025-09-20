from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from scripts.seed_league import DEFAULT_SEED, SeedSummary, seed_league
from domain.savepoint import create_savepoint

router = APIRouter(prefix="/league", tags=["league"])


class LeagueCreateRequest(BaseModel):
    seed: int | None = Field(default=None, description="Random seed for deterministic league seeding")


class LeagueCreateResponse(BaseModel):
    teams: int
    players: int
    plays_written: int


async def _run_seed(seed: int) -> SeedSummary:
    return await run_in_threadpool(seed_league, seed=seed, plays_dir=Path("data/plays"))


@router.post("/new", response_model=LeagueCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_league(payload: LeagueCreateRequest) -> LeagueCreateResponse:
    seed = payload.seed if payload.seed is not None else DEFAULT_SEED
    try:
        summary = await _run_seed(seed)
        create_savepoint(f"preseason_{seed}")
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LeagueCreateResponse(**asdict(summary))
