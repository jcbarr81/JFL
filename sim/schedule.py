
from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Dict, Iterable, List, Sequence, Tuple

from domain.models import Player
from sim.ruleset import GameConfig, GameSummary, simulate_game
from sim.statbook import StatBook


def make_schedule(team_ids: Sequence[str], *, seed: int = 0) -> List[Tuple[int, str, str]]:
    teams = list(team_ids)
    if len(teams) < 2:
        return []
    rng = Random(seed)
    pairings = [(home, away) for index, home in enumerate(teams) for away in teams[index + 1 :]]
    rng.shuffle(pairings)
    weeks = max(1, len(teams) - 1)
    schedule: List[Tuple[int, str, str]] = []
    for index, (home, away) in enumerate(pairings):
        week = index % weeks + 1
        schedule.append((week, home, away))
    for index, (home, away) in enumerate(pairings):
        week = (index + len(pairings)) % weeks + 1
        schedule.append((week, away, home))
    return schedule


@dataclass
class TeamSeason:
    team_id: str
    roster: Dict[str, Player]
    book: StatBook
    wins: int = 0
    losses: int = 0


@dataclass
class SeasonResult:
    standings: List[Tuple[str, int, int]]
    game_results: List[GameSummary]


def simulate_season(
    teams: Dict[str, Dict[str, Player]],
    *,
    seed: int = 0,
    config: GameConfig | None = None,
) -> SeasonResult:
    rng = Random(seed)
    schedule = make_schedule(list(teams.keys()), seed=seed)
    season_config = config or GameConfig()

    season_teams: Dict[str, TeamSeason] = {
        team_id: TeamSeason(team_id=team_id, roster=roster, book=StatBook())
        for team_id, roster in teams.items()
    }

    game_results: List[GameSummary] = []
    for week, home_id, away_id in schedule:
        home = season_teams[home_id]
        away = season_teams[away_id]
        summary = simulate_game(
            home_id,
            home.roster,
            home.book,
            away_id,
            away.roster,
            away.book,
            seed=rng.randint(0, 2**31 - 1),
            config=season_config,
        )
        game_results.append(summary)
        if summary.home_score > summary.away_score:
            home.wins += 1
            away.losses += 1
        elif summary.away_score > summary.home_score:
            away.wins += 1
            home.losses += 1
        else:
            if rng.random() < 0.5:
                home.wins += 1
                away.losses += 1
            else:
                away.wins += 1
                home.losses += 1

    standings = sorted(
        ((team.team_id, team.wins, team.losses) for team in season_teams.values()),
        key=lambda item: (-item[1], item[2], item[0]),
    )

    return SeasonResult(standings=standings, game_results=game_results)
