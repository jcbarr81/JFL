from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from typing import Dict, List, Tuple

from domain.models import Attributes, Player
from sim.schedule import SeasonResult, simulate_season
from sim.ruleset import GameConfig
from sim.statbook import StatBook
from sim.ruleset import TUNING


CALIBRATION_TARGETS = {
    "plays_per_team": (60, 75),
    "completion_pct": (0.58, 0.68),
    "yards_per_attempt": (6.0, 7.8),
    "pressure_rate": (0.05, 0.12),
    "sack_rate": (0.05, 0.09),
    "int_rate": (0.015, 0.03),
    "rush_ypc": (4.0, 4.7),
    "penalties": (4.0, 9.0),
}


@dataclass
class CalibrationMetrics:
    league_averages: Dict[str, float]
    metric_spreads: Dict[str, Tuple[float, float]]
    suggestions: Dict[str, Dict[str, float]]


def _player(player_id: str, position: str) -> Player:
    attrs = Attributes(
        speed=85,
        strength=80,
        agility=82,
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


def _build_roster(prefix: str) -> Dict[str, Player]:
    template = [
        "QB",
        "RB",
        "RB",
        "WR",
        "WR",
        "WR",
        "TE",
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
    return {f"{prefix}_{position}{index}": _player(f"{prefix}_{position}{index}", position) for index, position in enumerate(template, start=1)}


def _build_league(team_count: int, seed: int) -> Dict[str, Dict[str, Player]]:
    # seed reserved for future stochastic roster builds
    return {f"TEAM_{idx}": _build_roster(f"T{idx}") for idx in range(1, team_count + 1)}


def _compute_team_metrics(book: StatBook, games_played: int) -> Dict[str, float]:
    box = book.boxscore()
    players = box.get("players", {})
    offense = box.get("teams", {}).get("offense", {})

    completions = sum(stats.get("pass_completions", 0.0) for stats in players.values())
    attempts = sum(stats.get("pass_attempts", 0.0) for stats in players.values())
    pass_yards = sum(stats.get("pass_yards", 0.0) for stats in players.values())
    sacks_taken = sum(stats.get("sacks_taken", 0.0) for stats in players.values())
    interceptions = sum(stats.get("interceptions_thrown", 0.0) for stats in players.values())
    rush_yards = sum(stats.get("rush_yards", 0.0) for stats in players.values())
    rush_attempts = sum(stats.get("rush_attempts", 0.0) for stats in players.values())

    plays = offense.get("plays", 0.0)
    pressured_plays = offense.get("pressured_plays", 0.0)

    events = list(book.events)
    penalties = sum(1 for evt in events if evt.type == "penalty")

    games = max(1, games_played)

    metrics: Dict[str, float] = {}
    metrics["plays_per_team"] = plays / games if plays else 0.0
    metrics["completion_pct"] = completions / attempts if attempts else 0.0
    metrics["yards_per_attempt"] = pass_yards / attempts if attempts else 0.0
    metrics["pressure_rate"] = min(1.0, pressured_plays / attempts) if attempts else 0.0
    metrics["sack_rate"] = sacks_taken / attempts if attempts else 0.0
    metrics["int_rate"] = interceptions / attempts if attempts else 0.0
    metrics["rush_ypc"] = rush_yards / rush_attempts if rush_attempts else 0.0
    metrics["penalties"] = penalties / games
    return metrics


def _aggregate_metrics(result: SeasonResult) -> Dict[str, List[float]]:
    metrics: Dict[str, List[float]] = {key: [] for key in CALIBRATION_TARGETS.keys()}
    game_counts: Dict[str, int] = {}
    for summary in result.game_results:
        game_counts[summary.home_team] = game_counts.get(summary.home_team, 0) + 1
        game_counts[summary.away_team] = game_counts.get(summary.away_team, 0) + 1

    for team_id, book in result.team_books.items():
        team_metrics = _compute_team_metrics(book, game_counts.get(team_id, 0))
        for key, value in team_metrics.items():
            metrics.setdefault(key, []).append(value)
    return metrics


def _average_metrics(metric_lists: Dict[str, List[float]]) -> Dict[str, float]:
    averages: Dict[str, float] = {}
    for key, values in metric_lists.items():
        filtered = np.asarray([value for value in values if value >= 0], dtype=float)
        averages[key] = float(filtered.mean()) if filtered.size else 0.0
    return averages


def _suggest_adjustments(averages: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    mapping = {
        "completion_pct": "completion_mod",
        "pressure_rate": "pressure_mod",
        "sack_rate": "sack_distance",
        "int_rate": "int_mod",
        "yards_per_attempt": "yac_mod",
        "rush_ypc": "rush_block_mod",
        "penalties": "penalty_rate_mod",
    }
    suggestions: Dict[str, Dict[str, float]] = {}
    for metric, param in mapping.items():
        current_value = averages.get(metric, 0.0)
        target = CALIBRATION_TARGETS.get(metric)
        current_multiplier = getattr(TUNING, param)
        suggested_multiplier = current_multiplier
        if target and current_value > 0:
            lower, upper = target
            midpoint = (lower + upper) / 2
            if current_value < lower or current_value > upper:
                ratio = midpoint / current_value
                ratio = max(0.9, min(1.1, ratio))
                suggested_multiplier = round(current_multiplier * ratio, 4)
        suggestions[param] = {
            "current": round(current_multiplier, 4),
            "suggested": round(suggested_multiplier, 4),
        }
    return suggestions


def run_calibration(
    *,
    seasons: int = 5,
    team_count: int = 8,
    base_seed: int = 0,
    workers: int = 1,
    config: GameConfig | None = None,
) -> CalibrationMetrics:
    config = config or GameConfig()
    all_metrics: Dict[str, List[float]] = {key: [] for key in CALIBRATION_TARGETS.keys()}
    spreads: Dict[str, Tuple[float, float]] = {}

    for offset in range(seasons):
        seed = base_seed + offset
        teams = _build_league(team_count, seed)
        result = simulate_season(teams, seed=seed, config=config, workers=workers)
        season_metrics = _aggregate_metrics(result)
        for key, values in season_metrics.items():
            if not values:
                continue
            all_metrics.setdefault(key, []).extend(values)
            spread = (min(values), max(values))
            current = spreads.get(key)
            if current:
                spreads[key] = (min(current[0], spread[0]), max(current[1], spread[1]))
            else:
                spreads[key] = spread

    averages = _average_metrics(all_metrics)
    suggestions = _suggest_adjustments(averages)
    return CalibrationMetrics(league_averages=averages, metric_spreads=spreads, suggestions=suggestions)


__all__ = [
    "CalibrationMetrics",
    "run_calibration",
]
