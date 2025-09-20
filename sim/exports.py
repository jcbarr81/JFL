from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from sim.schedule import SeasonResult


def export_standings(result: SeasonResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["team_id", "wins", "losses"])
        for team_id, wins, losses in result.standings:
            writer.writerow([team_id, wins, losses])


def export_team_stats(result: SeasonResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["team_id", "phase", "metric", "value"]
        writer.writerow(header)
        for team_id, book in result.team_books.items():
            box = book.boxscore()
            for phase, stats in box.get("teams", {}).items():
                for metric, value in stats.items():
                    writer.writerow([team_id, phase, metric, value])


def export_player_stats(result: SeasonResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        header = ["team_id", "player_id", "metric", "value"]
        writer.writerow(header)
        for team_id, book in result.team_books.items():
            box = book.boxscore()
            for player_id, stats in box.get("players", {}).items():
                for metric, value in stats.items():
                    writer.writerow([team_id, player_id, metric, value])


def export_injuries(result: SeasonResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for team_id, book in result.team_books.items():
        for event in book.events:
            if event.type != "injury":
                continue
            records.append(
                {
                    "team_id": team_id,
                    "player_id": event.player_id,
                    "timestamp": event.timestamp,
                    "severity": (event.metadata or {}).get("severity"),
                }
            )
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def export_draft_results(picks: Iterable[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(picks), indent=2), encoding="utf-8")


__all__ = [
    "export_standings",
    "export_team_stats",
    "export_player_stats",
    "export_injuries",
    "export_draft_results",
]
