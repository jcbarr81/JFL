
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from random import Random
from typing import Dict, Iterable, List, Sequence, Tuple

from domain.models import Player
from sim.ruleset import GameConfig, GameSummary, simulate_game
from sim.seed import SeedManager
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
    team_books: Dict[str, StatBook]


def _simulate_game_task(
    home_team: str,
    home_roster: Dict[str, Player],
    away_team: str,
    away_roster: Dict[str, Player],
    seed: int,
    config: GameConfig,
) -> GameSummary:
    home_book = StatBook()
    away_book = StatBook()
    return simulate_game(
        home_team,
        home_roster,
        home_book,
        away_team,
        away_roster,
        away_book,
        seed=seed,
        config=config,
    )



def _finalize_game(
    summary: GameSummary,
    home: TeamSeason,
    away: TeamSeason,
    rng: Random,
    game_results: List[GameSummary],
) -> None:
    if summary.home_events:
        home.book.extend(summary.home_events)
    if summary.away_events:
        away.book.extend(summary.away_events)
    summary.home_events = []
    summary.away_events = []
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
    game_results.append(summary)



def simulate_season(
    teams: Dict[str, Dict[str, Player]],
    *,
    seed: int = 0,
    config: GameConfig | None = None,
    workers: int = 1,
) -> SeasonResult:
    rng = Random(seed)
    schedule_matrix = make_schedule(list(teams.keys()), seed=seed)
    season_config = config or GameConfig()

    season_teams: Dict[str, TeamSeason] = {
        team_id: TeamSeason(team_id=team_id, roster=roster, book=StatBook())
        for team_id, roster in teams.items()
    }

    games_by_week: Dict[int, List[Tuple[str, str]]] = {}
    seed_manager = SeedManager(base_seed=seed)
    season_label = str(seed)
    for week, home_id, away_id in schedule_matrix:
        games_by_week.setdefault(week, []).append((home_id, away_id))

    game_results: List[GameSummary] = []
    executor: ProcessPoolExecutor | None = None
    if workers > 1:
        executor = ProcessPoolExecutor(max_workers=workers)

    try:
        for week in sorted(games_by_week.keys()):
            games = games_by_week[week]
            if executor:
                futures = []
                for home_id, away_id in games:
                    home = season_teams[home_id]
                    away = season_teams[away_id]
                    game_seed = seed_manager.game_seed(season_label, week, home_id, away_id)
                    future = executor.submit(
                        _simulate_game_task,
                        home_id,
                        home.roster,
                        away_id,
                        away.roster,
                        game_seed,
                        season_config,
                    )
                    futures.append((home_id, away_id, future))
                for home_id, away_id, future in futures:
                    summary = future.result()
                    _finalize_game(summary, season_teams[home_id], season_teams[away_id], rng, game_results)
            else:
                for home_id, away_id in games:
                    home = season_teams[home_id]
                    away = season_teams[away_id]
                    game_seed = seed_manager.game_seed(season_label, week, home_id, away_id)
                    summary = _simulate_game_task(
                        home_id,
                        home.roster,
                        away_id,
                        away.roster,
                        game_seed,
                        season_config,
                    )
                    _finalize_game(summary, home, away, rng, game_results)
    finally:
        if executor:
            executor.shutdown()

    standings = sorted(
        ((team.team_id, team.wins, team.losses) for team in season_teams.values()),
        key=lambda item: (-item[1], item[2], item[0]),
    )

    team_books = {team_id: team.book for team_id, team in season_teams.items()}
    return SeasonResult(standings=standings, game_results=game_results, team_books=team_books)
