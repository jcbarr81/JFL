import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def load_play(name: str) -> dict:
    path = Path("data/plays") / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_validate_play_accepts_valid_payload() -> None:
    payload = load_play("quick_slant_right.json")
    response = client.post("/play/validate", json=payload)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_validate_play_rejects_non_monotonic_route() -> None:
    payload = {
        "play_id": "invalid_route",
        "name": "Invalid Route",
        "formation": "Shotgun",
        "personnel": "11",
        "play_type": "offense",
        "assignments": [
            {"player_id": "QB", "role": "pass", "route": None},
            {
                "player_id": "WR1",
                "role": "route",
                "route": [
                    {"timestamp": 0.0, "x": 0.0, "y": 0.0},
                    {"timestamp": 0.5, "x": 5.0, "y": 8.0},
                    {"timestamp": 0.4, "x": 10.0, "y": 12.0},
                ],
            },
        ],
    }

    response = client.post("/play/validate", json=payload)
    body = response.json()

    assert response.status_code == 400
    assert any("strictly increasing" in error["msg"] for error in body["detail"])


def test_validate_play_requires_ball_handler_on_offense() -> None:
    payload = {
        "play_id": "no_ball_handler",
        "name": "No Ball Handler",
        "formation": "I-Form",
        "personnel": "21",
        "play_type": "offense",
        "assignments": [
            {"player_id": "LT", "role": "block", "route": None},
            {"player_id": "LG", "role": "block", "route": None},
            {"player_id": "C", "role": "block", "route": None},
            {"player_id": "RG", "role": "block", "route": None},
            {"player_id": "RT", "role": "block", "route": None},
        ],
    }

    response = client.post("/play/validate", json=payload)
    body = response.json()

    assert response.status_code == 400
    assert any(
        "requires at least one 'pass' or 'carry'" in error["msg"]
        for error in body["detail"]
    )
