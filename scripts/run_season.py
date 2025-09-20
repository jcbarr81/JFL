import csv
from pathlib import Path
from random import Random

from domain.models import Attributes, Player
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
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "OL", "OL", "OL", "OL", "OL", "DL", "DL", "LB", "LB", "CB", "CB", "S", "S", "K", "P"]
    roster: dict[str, Player] = {}
    for index, position in enumerate(positions, start=1):
        player_id = f"{prefix}_{position}{index}"
        roster[player_id] = _player(player_id, position if position not in {"RB", "WR"} else position)
    return roster


def run_season(seed: int = 0) -> SeasonResult:
    teams = {f"TEAM_{index}": _build_roster(f"T{index}") for index in range(1, 9)}
    result = simulate_season(teams, seed=seed)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_standings(result, OUTPUT_DIR / "standings.csv")
    _write_team_stats(result, OUTPUT_DIR / "team_stats.csv")
    _write_player_stats(result, OUTPUT_DIR / "player_stats.csv")
    return result


def _write_standings(result: SeasonResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["team_id", "wins", "losses"])
        for team_id, wins, losses in result.standings:
            writer.writerow([team_id, wins, losses])


def _write_team_stats(result: SeasonResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["team_id", "games", "points_for", "points_against"])
        aggregates: dict[str, dict[str, float]] = {}
        for summary in result.game_results:
            aggregates.setdefault(summary.home_team, {"games": 0, "pf": 0, "pa": 0})
            aggregates.setdefault(summary.away_team, {"games": 0, "pf": 0, "pa": 0})
            aggregates[summary.home_team]["games"] += 1
            aggregates[summary.home_team]["pf"] += summary.home_score
            aggregates[summary.home_team]["pa"] += summary.away_score
            aggregates[summary.away_team]["games"] += 1
            aggregates[summary.away_team]["pf"] += summary.away_score
            aggregates[summary.away_team]["pa"] += summary.home_score
        for team_id, stats in sorted(aggregates.items()):
            writer.writerow([
                team_id,
                int(stats["games"]),
                int(stats["pf"]),
                int(stats["pa"]),
            ])


def _write_player_stats(result: SeasonResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["team_id", "player_id", "statbook_key", "value"])
        for summary in result.game_results:
            for team_id, boxscore in (
                (summary.home_team, summary.home_boxscore),
                (summary.away_team, summary.away_boxscore),
            ):
                for player_id, stats in boxscore["players"].items():
                    for key, value in stats.items():
                        writer.writerow([team_id, player_id, key, value])


if __name__ == "__main__":
    run_season(seed=42)
