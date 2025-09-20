from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import game as game_api, league as league_api, plays as plays_api, season as season_api, stats as stats_api
from domain.db import create_all

APP_VERSION = "0.1.0"

app = FastAPI(
    title="Gridiron Sim API",
    version=APP_VERSION,
    description="Public surface for league management and simulations.",
)

create_all()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"http://localhost(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(league_api.router)
app.include_router(season_api.router)
app.include_router(game_api.router)
app.include_router(stats_api.router)
app.include_router(plays_api.router)


@app.get("/health")
async def read_health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/version")
async def read_version() -> str:
    return APP_VERSION
