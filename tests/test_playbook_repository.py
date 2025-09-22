import json
from pathlib import Path

from domain.playbook import PlaybookRepository


def _write_play(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _offense_play(play_id: str = "slant_right", name: str = "Slant Right") -> dict:
    return {
        "play_id": play_id,
        "name": name,
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
                    {"timestamp": 1.0, "x": 2.0, "y": 10.0},
                ],
            },
            {"player_id": "RB1", "role": "carry", "route": None},
        ],
    }


def _defense_play(play_id: str = "cover_two", name: str = "Cover Two") -> dict:
    return {
        "play_id": play_id,
        "name": name,
        "formation": "Nickel",
        "personnel": "Nickel",
        "play_type": "defense",
        "assignments": [
            {
                "player_id": "CB1",
                "role": "defend",
                "route": [
                    {"timestamp": 0.0, "x": -12.0, "y": 0.0},
                    {"timestamp": 1.0, "x": -10.0, "y": 12.0},
                ],
            },
            {
                "player_id": "S1",
                "role": "defend",
                "route": [
                    {"timestamp": 0.0, "x": 5.0, "y": 0.0},
                    {"timestamp": 1.1, "x": 5.0, "y": 15.0},
                ],
            },
            {
                "player_id": "LB1",
                "role": "rush",
                "route": [
                    {"timestamp": 0.0, "x": 0.0, "y": 0.0},
                    {"timestamp": 0.8, "x": 0.0, "y": 8.0},
                ],
            },
        ],
    }


def test_list_plays_filters_by_type(tmp_path: Path) -> None:
    plays_dir = tmp_path / "plays"
    plays_dir.mkdir()
    _write_play(plays_dir / "slant_right.json", _offense_play())
    _write_play(plays_dir / "cover_two.json", _defense_play())

    repo = PlaybookRepository(plays_dir=plays_dir, user_home=tmp_path / "home")
    offense = repo.list_plays("offense")
    defense = repo.list_plays("defense")

    assert len(offense) == 1
    assert offense[0].name == "Slant Right"
    assert offense[0].usage.calls > 0

    assert len(defense) == 1
    assert defense[0].play_type == "defense"


def test_update_tags_and_mirror(tmp_path: Path) -> None:
    plays_dir = tmp_path / "plays"
    plays_dir.mkdir()
    _write_play(plays_dir / "slant_right.json", _offense_play())

    repo = PlaybookRepository(plays_dir=plays_dir, user_home=tmp_path / "home")
    repo.update_tags("slant_right", ["base", "third_down"])

    metadata_file = tmp_path / "home" / "playbooks.json"
    assert metadata_file.exists()
    data = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert data["slant_right"]["tags"] == ["base", "third_down"]

    mirrored = repo.mirror_play("slant_right", new_play_id="slant_left")
    assert mirrored.play_id == "slant_left"
    mirrored_path = plays_dir / "slant_left.json"
    assert mirrored_path.exists()
    payload = json.loads(mirrored_path.read_text(encoding="utf-8"))
    first_route = payload["assignments"][1]["route"]
    assert first_route[0]["x"] == 5.0  # mirrored across the axis
    summaries = repo.list_plays("offense")
    assert any(summary.play_id == "slant_left" for summary in summaries)


