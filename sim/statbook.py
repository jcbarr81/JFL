from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class PlayEvent:
    type: str
    timestamp: float
    team: Optional[str] = None
    player_id: Optional[str] = None
    target_id: Optional[str] = None
    yards: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


def _player_template() -> Dict[str, float]:
    return {
        "pass_attempts": 0,
        "pass_completions": 0,
        "pass_yards": 0.0,
        "pressures": 0,
        "sacks_taken": 0,
        "interceptions_thrown": 0,
        "rush_attempts": 0,
        "rush_yards": 0.0,
        "receptions": 0,
        "receiving_yards": 0.0,
        "tackles": 0,
        "sacks": 0,
        "interceptions_made": 0,
        "pressures_generated": 0,
    }


def _team_template() -> Dict[str, float]:
    return {
        "plays": 0,
        "yards": 0.0,
        "successes": 0,
        "epa": 0.0,
        "pass_attempts": 0,
        "rush_attempts": 0,
        "pressures": 0,
        "sacks": 0,
        "turnovers": 0,
    }


class StatBook:
    """Accumulates play events and reduces them into box scores and rates."""

    def __init__(self) -> None:
        self._events: List[PlayEvent] = []

    def note(self, event: PlayEvent) -> None:
        self._events.append(event)

    def extend(self, events: Iterable[PlayEvent]) -> None:
        self._events.extend(events)

    @property
    def events(self) -> List[PlayEvent]:
        return list(self._events)

    def boxscore(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        players: Dict[str, Dict[str, float]] = defaultdict(_player_template)
        teams: Dict[str, Dict[str, float]] = defaultdict(_team_template)

        for event in self._events:
            meta = event.metadata or {}

            if event.type == "pass_attempt":
                passer_id = event.player_id or meta.get("passer_id")
                if passer_id:
                    players[passer_id]["pass_attempts"] += 1
                teams["offense"]["pass_attempts"] += 1

            elif event.type == "pass_completion":
                passer_id = meta.get("passer_id")
                receiver_id = meta.get("receiver_id") or event.player_id
                if passer_id:
                    players[passer_id]["pass_completions"] += 1
                if receiver_id:
                    players[receiver_id]["receptions"] += 1

            elif event.type == "pass_incomplete":
                passer_id = event.player_id or meta.get("passer_id")
                if passer_id:
                    players[passer_id]["pass_attempts"] += 0  # ensure key exists

            elif event.type == "rush_attempt":
                runner_id = event.player_id or meta.get("runner_id")
                if runner_id:
                    players[runner_id]["rush_attempts"] += 1
                teams["offense"]["rush_attempts"] += 1

            elif event.type == "pressure":
                passer_id = meta.get("passer_id")
                defender_id = meta.get("defender_id") or event.player_id
                if passer_id:
                    players[passer_id]["pressures"] += 1
                if defender_id:
                    players[defender_id]["pressures_generated"] += 1
                teams["offense"]["pressures"] += 1

            elif event.type == "sack":
                qb_id = meta.get("qb_id") or event.target_id
                defender_id = event.player_id
                if qb_id:
                    players[qb_id]["sacks_taken"] += 1
                if defender_id:
                    players[defender_id]["sacks"] += 1
                teams["defense"]["sacks"] += 1

            elif event.type == "interception":
                passer_id = meta.get("passer_id")
                defender_id = meta.get("defender_id") or event.player_id
                if passer_id:
                    players[passer_id]["interceptions_thrown"] += 1
                if defender_id:
                    players[defender_id]["interceptions_made"] += 1
                teams["offense"]["turnovers"] += 1

            elif event.type == "tackle":
                tackler_id = event.player_id
                if tackler_id:
                    players[tackler_id]["tackles"] += 1

            if event.type == "play_end":
                play_type = meta.get("play_type") or "unknown"
                teams["offense"]["plays"] += 1
                teams["offense"]["yards"] += event.yards
                teams["offense"]["epa"] += event.yards * 0.05
                if meta.get("success"):
                    teams["offense"]["successes"] += 1
                if meta.get("interception"):
                    teams["offense"]["turnovers"] += 1

                passer_id = meta.get("passer_id")
                runner_id = meta.get("runner_id")
                receiver_id = meta.get("receiver_id")

                if play_type == "pass":
                    if passer_id:
                        players[passer_id]["pass_yards"] += event.yards
                    if receiver_id:
                        players[receiver_id]["receiving_yards"] += event.yards
                elif play_type == "run" and runner_id:
                    players[runner_id]["rush_yards"] += event.yards

        return {"players": dict(players), "teams": dict(teams)}

    def advanced_rates(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        box = self.boxscore()
        passer_rates: Dict[str, Dict[str, float]] = {}
        for player_id, stats in box["players"].items():
            attempts = stats["pass_attempts"]
            if attempts:
                passer_rates[player_id] = {
                    "completion_pct": stats["pass_completions"] / attempts if attempts else 0.0,
                    "yards_per_attempt": stats["pass_yards"] / attempts if attempts else 0.0,
                    "pressure_rate": stats["pressures"] / attempts if attempts else 0.0,
                    "sack_rate": stats["sacks_taken"] / attempts if attempts else 0.0,
                }

        team_rates: Dict[str, Dict[str, float]] = {}
        for team, stats in box["teams"].items():
            plays = stats["plays"]
            pass_attempts = stats["pass_attempts"]
            team_rates[team] = {
                "success_rate": stats["successes"] / plays if plays else 0.0,
                "epa_per_play": stats["epa"] / plays if plays else 0.0,
                "pressure_rate": stats["pressures"] / pass_attempts if pass_attempts else 0.0,
            }

        return {"passers": passer_rates, "teams": team_rates}
