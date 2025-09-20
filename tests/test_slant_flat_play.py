from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from domain.models import Attributes, Play, Player
from sim.engine import simulate_play

client = TestClient(app)


def _player(
    player_id: str,
    position: str,
    *,
    speed: int = 90,
    strength: int = 85,
    agility: int = 88,
    awareness: int = 88,
    catching: int = 88,
    tackling: int = 88,
    throwing_power: int = 88,
    accuracy: int = 88,
) -> Player:
    attrs = Attributes(
        speed=speed,
        strength=strength,
        agility=agility,
        awareness=awareness,
        catching=catching,
        tackling=tackling,
        throwing_power=throwing_power,
        accuracy=accuracy,
    )
    return Player(
        player_id=player_id,
        name=player_id,
        position=position,
        jersey_number=12,
        attributes=attrs,
    )


def _load_slant_offense() -> dict[str, Player]:
    roster: dict[str, Player] = {}
    roster["QB1"] = _player("QB1", "QB", accuracy=94, throwing_power=92, awareness=93)
    roster["RB1"] = _player("RB1", "RB", speed=92, agility=93, catching=82)
    roster["WR1"] = _player("WR1", "WR", speed=97, catching=94, agility=95)
    roster["WR2"] = _player("WR2", "WR", speed=94, catching=90, agility=92)
    roster["WR3"] = _player("WR3", "WR", speed=92, catching=88, agility=91)
    roster["TE1"] = _player("TE1", "TE", speed=86, catching=90, agility=84, strength=88)
    roster["LT"] = _player("LT", "OL", strength=95, tackling=80, speed=70, agility=70)
    roster["LG"] = _player("LG", "OL", strength=95, tackling=80, speed=70, agility=70)
    roster["C"] = _player("C", "OL", strength=95, tackling=80, speed=70, agility=70)
    roster["RG"] = _player("RG", "OL", strength=95, tackling=80, speed=70, agility=70)
    roster["RT"] = _player("RT", "OL", strength=95, tackling=80, speed=70, agility=70)
    return roster


def _load_sample_defense(count: int = 11) -> dict[str, Player]:
    roster: dict[str, Player] = {}
    for index in range(count):
        identifier = f"DEF{index}"
        roster[identifier] = _player(
            identifier,
            position="CB" if index < 4 else "LB",
            speed=88,
            agility=85,
            awareness=82,
            tackling=90,
            catching=50,
        )
    return roster


def _load_play(path: str) -> dict:
    payload = Path("data/plays") / path
    return json.loads(payload.read_text(encoding="utf-8"))


def test_slant_flat_right_validates_and_simulates() -> None:
    payload = _load_play("slant_flat_right.json")
    play = Play.model_validate(payload)

    response = client.post("/play/validate", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    offense = _load_slant_offense()
    defense = _load_sample_defense()

    result = simulate_play(play, offense, defense, seed=2048)

    assert result.play_type == "pass"
    assert result.sack is False
    assert result.interception is False
    assert result.yards_gained >= 0
    assert any(event.type == "pass_completion" for event in result.events)


def test_slant_flat_left_validates() -> None:
    payload = _load_play("slant_flat_left.json")
    play = Play.model_validate(payload)

    response = client.post("/play/validate", json=payload)
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    # Ensure role expectations hold.
    route_roles = {assignment.role for assignment in play.assignments if assignment.route}
    assert "route" in route_roles
