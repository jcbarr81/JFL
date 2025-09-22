from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ValidationError

from domain.models import Play
from domain.playbook import (
    PlayAlreadyExistsError,
    PlayValidationError,
    PlaybookError,
    PlaybookRepository,
    validate_play as domain_validate_play,
)

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


def _repository() -> PlaybookRepository:
    return PlaybookRepository()


@router.get("/list", response_model=list[PlaySummary])
async def list_plays() -> list[PlaySummary]:
    repo = _repository()
    summaries = repo.list_plays()
    return [
        PlaySummary(
            play_id=item.play_id,
            name=item.name,
            formation=item.formation,
            personnel=item.personnel,
            play_type=item.play_type,
            path=str(item.path),
        )
        for item in summaries
    ]


@router.post(
    "/import",
    response_model=PlayImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_play(play: Play, overwrite: bool = Query(False, description="Overwrite existing play file")) -> PlayImportResponse:
    repo = _repository()
    try:
        repo.save_play(play, overwrite=overwrite)
    except PlayAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PlayValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors)
    except PlaybookError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    _, path = repo.load_play(play.play_id)
    return PlayImportResponse(play_id=play.play_id, path=str(path))


@router.post("/validate", response_model=PlayValidationResponse)
async def validate_play(payload: dict[str, Any]) -> PlayValidationResponse:
    try:
        play = Play.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=_sanitize_error_context(exc.errors()),
        ) from exc

    errors = domain_validate_play(play)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    return PlayValidationResponse(ok=True)
