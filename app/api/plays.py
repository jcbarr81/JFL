from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from domain.models import Assignment, Play

router = APIRouter(prefix="/play", tags=["plays"])


class PlayValidationResponse(BaseModel):
    ok: bool


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
