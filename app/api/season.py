from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import db_session
from domain.db import BoxScoreRow, GameRow, PlayerRow, SeasonRow, TeamRow
from domain.savepoint import create_savepoint
from sim.exports import export_draft_results, export_injuries, export_player_stats, export_standings, export_team_stats
from domain.models import Attributes, Player
from sim.schedule import SeasonResult, make_schedule, simulate_season

router = APIRouter(prefix="/season", tags=["season"])


class SeasonRunRequest(BaseModel):
    seed: int = Field(default=0, description="Base random seed for simulations")
    seasons: int = Field(default=1, ge=1, le=10, description="Number of seasons to simulate")
    workers: int = Field(default=1, ge=1, le=4, description="Parallel worker threads to use")
    starting_year: int | None = Field(default=None, description="Optional starting year for generated seasons")
    description: str | None = Field(default=None, description="Optional description applied to each season row")


class StandingEntry(BaseModel):
    team_id: str
    wins: int
    losses: int


class GameResultEntry(BaseModel):
    game_id: str
    week: int
    home_team: str
    away_team: str
    home_score: int
    away_score: int


class SeasonRunSummary(BaseModel):
    season_id: str
    year: int
    seed: int
    standings: List[StandingEntry]
    games: List[GameResultEntry]


class SeasonRunResponse(BaseModel):
    seasons: List[SeasonRunSummary]


@dataclass
class _SimPayload:
    seed: int
    schedule: List[Tuple[int, str, str]]
    result: SeasonResult


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


def _players_by_team(session: Session) -> Dict[str, List[PlayerRow]]:
    players = session.exec(select(PlayerRow)).all()
    mapping: Dict[str, List[PlayerRow]] = {}
    for player in players:
        team_id = player.team_id
        if not team_id:
            continue
        mapping.setdefault(team_id, []).append(player)
    return mapping


def _roster_for_team(team_id: str, rows: Iterable[PlayerRow]) -> Dict[str, Player]:
    roster: Dict[str, Player] = {}
    for row in rows:
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


def _build_rosters(teams: List[TeamRow], players: Dict[str, List[PlayerRow]]) -> Dict[str, Dict[str, Player]]:
    rosters: Dict[str, Dict[str, Player]] = {}
    for team in teams:
        team_players = players.get(team.team_id, [])
        if not team_players:
            continue
        rosters[team.team_id] = _roster_for_team(team.team_id, team_players)
    return rosters


def _persist_season(
    session: Session,
    season_row: SeasonRow,
    schedule: List[Tuple[int, str, str]],
    result: SeasonResult,
    *,
    midseason_savepoint: str | None = None,
) -> List[GameResultEntry]:
    session.add(season_row)
    games_payload: List[GameResultEntry] = []
    total_games = len(result.game_results)
    midpoint = total_games // 2 if total_games > 1 else 0
    mid_save_created = False
    for index, ((week, home_team, away_team), summary) in enumerate(zip(schedule, result.game_results)):
        game_id = f"{season_row.season_id}-W{week:02d}-{home_team}-{away_team}-{uuid4().hex[:6]}"
        game_row = GameRow(
            game_id=game_id,
            season_id=season_row.season_id,
            week=week,
            home_team_id=home_team,
            away_team_id=away_team,
            played=True,
        )
        session.add(game_row)

        session.add(
            BoxScoreRow(
                game_id=game_id,
                team_id=home_team,
                player_id=None,
                stat_type="team_game",
                stat_payload=summary.home_boxscore.get("teams", {}),
            )
        )
        for player_id, stats in summary.home_boxscore.get("players", {}).items():
            session.add(
                BoxScoreRow(
                    game_id=game_id,
                    team_id=home_team,
                    player_id=player_id,
                    stat_type="player_game",
                    stat_payload=stats,
                )
            )
        session.add(
            BoxScoreRow(
                game_id=game_id,
                team_id=away_team,
                player_id=None,
                stat_type="team_game",
                stat_payload=summary.away_boxscore.get("teams", {}),
            )
        )
        for player_id, stats in summary.away_boxscore.get("players", {}).items():
            session.add(
                BoxScoreRow(
                    game_id=game_id,
                    team_id=away_team,
                    player_id=player_id,
                    stat_type="player_game",
                    stat_payload=stats,
                )
            )

        games_payload.append(
            GameResultEntry(
                game_id=game_id,
                week=week,
                home_team=home_team,
                away_team=away_team,
                home_score=summary.home_score,
                away_score=summary.away_score,
            )
        )
        if midseason_savepoint and not mid_save_created and midpoint and index + 1 >= midpoint:
            session.commit()
            create_savepoint(midseason_savepoint)
            mid_save_created = True
    return games_payload


def _simulate_single_season(
    teams: List[TeamRow],
    players: Dict[str, List[PlayerRow]],
    seed: int,
    workers: int,
) -> _SimPayload:
    rosters = _build_rosters(teams, players)
    if not rosters:
        raise ValueError("No rosters available for simulation")
    schedule = make_schedule(list(rosters.keys()), seed=seed)
    result = simulate_season(rosters, seed=seed, workers=workers)
    return _SimPayload(seed=seed, schedule=schedule, result=result)


@router.post("/run", response_model=SeasonRunResponse, status_code=status.HTTP_201_CREATED)
async def run_season(
    payload: SeasonRunRequest,
    session: Session = Depends(db_session),
) -> SeasonRunResponse:
    teams = session.exec(select(TeamRow)).all()
    if not teams:
        raise HTTPException(status_code=400, detail="No teams present in database. Seed a league first.")
    players = _players_by_team(session)
    if not players:
        raise HTTPException(status_code=400, detail="No players associated with teams.")

    seeds = [payload.seed + index for index in range(payload.seasons)]

    if payload.seasons > 1 and payload.workers > 1:
        game_workers = max(1, payload.workers // payload.seasons)
    else:
        game_workers = payload.workers
    if game_workers < 1:
        game_workers = 1

    def runner(seed: int) -> _SimPayload:
        return _simulate_single_season(teams, players, seed, game_workers)

    sim_results: List[_SimPayload] = []
    if payload.workers > 1 and payload.seasons > 1:
        with ThreadPoolExecutor(max_workers=payload.workers) as executor:
            futures = [executor.submit(runner, seed) for seed in seeds]
            for future in futures:
                try:
                    sim_results.append(future.result())
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        for seed in seeds:
            try:
                sim_results.append(await run_in_threadpool(runner, seed))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    summaries: List[SeasonRunSummary] = []
    base_year = payload.starting_year or 2025
    for index, sim_payload in enumerate(sim_results):
        season_id = f"SEASON-{uuid4().hex[:8]}"
        season_row = SeasonRow(
            season_id=season_id,
            year=base_year + index,
            description=payload.description,
            is_current=False,
        )
        midseason_name = f"{season_id}_midseason"
        games = _persist_season(
            session,
            season_row,
            sim_payload.schedule,
            sim_payload.result,
            midseason_savepoint=midseason_name,
        )
        session.commit()
        pre_draft_name = f"{season_id}_pre_draft"
        create_savepoint(pre_draft_name)

        export_root = Path("data/exports") / season_id
        export_root.mkdir(parents=True, exist_ok=True)
        export_standings(sim_payload.result, export_root / "standings.csv")
        export_team_stats(sim_payload.result, export_root / "team_stats.csv")
        export_player_stats(sim_payload.result, export_root / "player_stats.csv")
        export_injuries(sim_payload.result, export_root / "injuries.json")
        draft_results = [
            {"team_id": team_id, "round": 1, "overall": order + 1}
            for order, (team_id, _, _) in enumerate(sim_payload.result.standings)
        ]
        export_draft_results(draft_results, export_root / "draft_results.json")

        standings = [
            StandingEntry(team_id=team_id, wins=wins, losses=losses)
            for team_id, wins, losses in sim_payload.result.standings
        ]
        summaries.append(
            SeasonRunSummary(
                season_id=season_id,
                year=season_row.year,
                seed=sim_payload.seed,
                standings=standings,
                games=games,
            )
        )
    session.commit()
    return SeasonRunResponse(seasons=summaries)
