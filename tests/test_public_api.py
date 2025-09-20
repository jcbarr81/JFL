from __future__ import annotations

from pathlib import Path

import base64
import json
import zlib

from fastapi.testclient import TestClient
from sqlmodel import select

from app.main import app
from domain.db import PlayerRow, get_session

client = TestClient(app)


def _sample_play_payload(play_id: str) -> dict:
    return {
        "play_id": play_id,
        "name": "API Test Play",
        "formation": "Trips Right",
        "personnel": "11",
        "play_type": "offense",
        "assignments": [
            {"player_id": "QB1", "role": "pass", "route": None},
            {
                "player_id": "WR1",
                "role": "route",
                "route": [
                    {"timestamp": 0.0, "x": -5.0, "y": 0.0},
                    {"timestamp": 1.2, "x": -1.0, "y": 12.0},
                ],
            },
            {"player_id": "RB1", "role": "carry", "route": None},
            {"player_id": "LT", "role": "block", "route": None},
            {"player_id": "LG", "role": "block", "route": None},
            {"player_id": "C", "role": "block", "route": None},
            {"player_id": "RG", "role": "block", "route": None},
            {"player_id": "RT", "role": "block", "route": None},
        ],
    }


def test_league_new_endpoint_creates_league() -> None:
    response = client.post("/league/new", json={"seed": 2025})
    assert response.status_code == 201
    body = response.json()
    assert body["teams"] >= 4
    assert body["players"] > 0


def test_play_import_and_list_round_trip() -> None:
    play_id = "api_test_play"
    payload = _sample_play_payload(play_id)

    response = client.post("/play/import", json=payload)
    assert response.status_code == 201
    body = response.json()
    path = Path(body["path"])
    assert path.exists()

    listing = client.get("/play/list")
    assert listing.status_code == 200
    plays = listing.json()
    assert any(item["play_id"] == play_id for item in plays)

    path.unlink(missing_ok=True)


def test_game_simulation_and_stats_endpoints() -> None:
    simulate_payload = {
        "home_team_id": "ATX",
        "away_team_id": "BOS",
        "seed": 1234,
        "week": 1,
        "season_id": None,
        "save": True,
    }
    response = client.post("/game/simulate", json=simulate_payload)
    assert response.status_code == 201
    game_body = response.json()
    assert game_body["game_id"]
    assert game_body["home_score"] >= 0
    assert game_body["away_score"] >= 0
    assert game_body["events_blob"]
    decoded = base64.b64decode(game_body["events_blob"])
    payload = json.loads(zlib.decompress(decoded).decode("utf-8"))
    assert "home" in payload and "away" in payload

    team_stats = client.get("/stats/team/ATX")
    assert team_stats.status_code == 200
    team_body = team_stats.json()
    assert team_body["games"] >= 1
    assert "offense" in team_body["totals"]

    with get_session() as session:
        player_row = session.exec(select(PlayerRow).where(PlayerRow.team_id == "ATX")).first()
    assert player_row is not None

    player_stats = client.get(f"/stats/player/{player_row.player_id}")
    assert player_stats.status_code == 200
    player_body = player_stats.json()
    assert player_body["games"] >= 1


def test_season_run_endpoint_returns_summary() -> None:
    response = client.post("/season/run", json={"seed": 77, "seasons": 1, "workers": 1})
    assert response.status_code == 201
    body = response.json()
    assert "seasons" in body
    assert len(body["seasons"]) == 1
    summary = body["seasons"][0]
    assert summary["standings"]
    assert summary["games"]


def test_stats_team_not_found_returns_404() -> None:
    response = client.get("/stats/team/UNKNOWN")
    assert response.status_code == 404


def test_stats_player_not_found_returns_404() -> None:
    response = client.get("/stats/player/UNKNOWN")
    assert response.status_code == 404
