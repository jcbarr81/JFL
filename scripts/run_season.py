from __future__ import annotations

import os
from pathlib import Path
from domain.models import Attributes, Player
from sim.exports import export_draft_results, export_injuries, export_player_stats, export_standings, export_team_stats
from sim.schedule import SeasonResult, simulate_season

OUTPUT_DIR = Path("build/season")


def _player(player_id: str, position: str) -> Player:
    attrs = Attributes(
        speed=85,
        strength=82,
        agility=84,
        awareness=78,
        catching=72,
        tackling=74,
        throwing_power=70,
        accuracy=70,
    )
    return Player(
        player_id=player_id,
        name=player_id,
        position=position,
        jersey_number=12,
        attributes=attrs,
    )


def _build_roster(prefix: str) -> dict[str, Player]:
    positions = [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "WR",
        "TE",
        "OL",
        "OL",
        "OL",
        "OL",
        "OL",
        "DL",
        "DL",
        "LB",
        "LB",
        "CB",
        "CB",
        "S",
        "S",
        "K",
        "P",
    ]
    roster: dict[str, Player] = {}
    for index, position in enumerate(positions, start=1):
        player_id = f"{prefix}_{position}{index}"
        roster[player_id] = _player(player_id, position if position not in {"RB", "WR"} else position)
    return roster


def run_season(seed: int = 0, workers: int | None = None) -> SeasonResult:
    teams = {f"TEAM_{index}": _build_roster(f"T{index}") for index in range(1, 9)}
    worker_count = workers or max(1, (os.cpu_count() or 1))
    result = simulate_season(teams, seed=seed, workers=worker_count)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    export_standings(result, OUTPUT_DIR / "standings.csv")
    export_team_stats(result, OUTPUT_DIR / "team_stats.csv")
    export_player_stats(result, OUTPUT_DIR / "player_stats.csv")
    export_injuries(result, OUTPUT_DIR / "injuries.json")
    draft_results = [
        {"team_id": team_id, "round": 1, "overall": order + 1}
        for order, (team_id, _, _) in enumerate(result.standings)
    ]
    export_draft_results(draft_results, OUTPUT_DIR / "draft_results.json")
    return result


if __name__ == "__main__":
    run_season(seed=42)
