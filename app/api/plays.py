from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ValidationError

from domain.models import Play

router = APIRouter(prefix="/play", tags=["plays"])


class PlayValidationResponse(BaseModel):
    ok: bool


class PlaySummary(BaseModel):
    play_id: str
    name: str
    formation: str
    personnel: str
    play_type: str
    path: str


class PlayImportResponse(BaseModel):
    play_id: str
    path: str


def _sanitize_error_context(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for error in errors:
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error = {**error, "ctx": {key: str(value) for key, value in ctx.items()}}
        sanitized.append(error)
    return sanitized


def _role_requires_route(role: str) -> bool:
    return role in {"route", "defend", "rush"}


def _validate_play(play: Play) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    seen_players: set[str] = set()

    for index, assignment in enumerate(play.assignments):
        if assignment.player_id in seen_players:
            errors.append(
                {
                    "loc": ["assignments", index, "player_id"],
                    "msg": f"duplicate assignment for player '{assignment.player_id}'",
                    "type": "value_error.duplicate",
                }
            )
        else:
            seen_players.add(assignment.player_id)

        if _role_requires_route(assignment.role) and not assignment.route:
            errors.append(
                {
                    "loc": ["assignments", index, "route"],
                    "msg": f"role '{assignment.role}' requires a route",
                    "type": "value_error.route_required",
                }
            )

    role_counts = Counter(assignment.role for assignment in play.assignments)

    if play.play_type == "offense":
        if role_counts.get("pass", 0) > 1:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "offense play can have at most one 'pass' assignment",
                    "type": "value_error.role_count",
                }
            )
        if role_counts.get("pass", 0) + role_counts.get("carry", 0) == 0:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "offense play requires at least one 'pass' or 'carry' assignment",
                    "type": "value_error.role_required",
                }
            )
    elif play.play_type == "special_teams":
        if role_counts.get("kick", 0) != 1:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "special_teams play requires exactly one 'kick' assignment",
                    "type": "value_error.role_required",
                }
            )
    elif play.play_type == "defense":
        if role_counts.get("defend", 0) + role_counts.get("rush", 0) == 0:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "defense play requires at least one 'defend' or 'rush' assignment",
                    "type": "value_error.role_required",
                }
            )

    return errors


def _play_directory() -> Path:
    directory = Path("data/plays")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


@router.get("/list", response_model=list[PlaySummary])
async def list_plays() -> list[PlaySummary]:
    directory = _play_directory()
    summaries: list[PlaySummary] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            play = Play.model_validate(payload)
            errors = _validate_play(play)
            if errors:
                continue
            summaries.append(
                PlaySummary(
                    play_id=play.play_id,
                    name=play.name,
                    formation=play.formation,
                    personnel=play.personnel,
                    play_type=play.play_type,
                    path=str(path),
                )
            )
        except (json.JSONDecodeError, ValidationError):
            continue
    return summaries


@router.post(
    "/import",
    response_model=PlayImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_play(play: Play, overwrite: bool = Query(False, description="Overwrite existing play file")) -> PlayImportResponse:
    errors = _validate_play(play)
    if errors:
        raise HTTPException(status_code=400, detail=_sanitize_error_context(errors))

    directory = _play_directory()
    path = directory / f"{play.play_id}.json"
    if path.exists() and not overwrite:
        raise HTTPException(status_code=409, detail=f"Play '{play.play_id}' already exists. Use overwrite=true to replace it.")

    payload = play.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return PlayImportResponse(play_id=play.play_id, path=str(path))


@router.post("/validate", response_model=PlayValidationResponse)
async def validate_play(payload: dict[str, Any]) -> PlayValidationResponse:
    try:
        play = Play.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail=_sanitize_error_context(exc.errors())
        ) from exc

    errors = _validate_play(play)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    return PlayValidationResponse(ok=True)
