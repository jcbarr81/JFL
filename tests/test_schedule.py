from domain.models import Attributes, Player
from sim.schedule import make_schedule, simulate_season
from sim.statbook import StatBook


def _player(pid: str, pos: str) -> Player:
    attrs = Attributes(
        speed=85,
        strength=82,
        agility=80,
        awareness=78,
        catching=70,
        tackling=70,
        throwing_power=68,
        accuracy=68,
    )
    return Player(player_id=pid, name=pid, position=pos, jersey_number=10, attributes=attrs)


def _roster(prefix: str) -> dict[str, Player]:
    positions = ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "OL", "OL", "OL", "OL", "OL", "DL", "DL", "LB", "LB", "CB", "CB", "S", "S", "K", "P"]
    return {f"{prefix}_{index}": _player(f"{prefix}_{index}", pos if pos != "RB" else "RB") for index, pos in enumerate(positions, start=1)}


def test_make_schedule_balanced_home_away():
    teams = ["A", "B", "C", "D"]
    schedule = make_schedule(teams, seed=0)
    home_counts = {team: 0 for team in teams}
    away_counts = {team: 0 for team in teams}
    for _, home, away in schedule:
        home_counts[home] += 1
        away_counts[away] += 1
    for team in teams:
        assert abs(home_counts[team] - away_counts[team]) <= 1


def test_simulate_season_completes():
    teams = {f"TEAM{idx}": _roster(f"TEAM{idx}") for idx in range(4)}
    result = simulate_season(teams, seed=1)
    assert len(result.game_results) == len(make_schedule(list(teams.keys())))
    total_games = sum(w + l for _, w, l in result.standings)
    assert total_games == len(result.game_results) * 2


def test_simulate_season_parallel_matches_serial() -> None:
    serial_teams = {f"TEAM{idx}": _roster(f"SERIAL{idx}") for idx in range(4)}
    parallel_teams = {f"TEAM{idx}": _roster(f"SERIAL{idx}") for idx in range(4)}
    seed = 2
    serial = simulate_season(serial_teams, seed=seed, workers=1)
    parallel = simulate_season(parallel_teams, seed=seed, workers=2)
    assert parallel.standings == serial.standings
    assert len(parallel.game_results) == len(serial.game_results)
