from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from random import Random
from sim.special_teams import PenaltyType, apply_penalty, attempt_field_goal
from typing import Dict, Iterable, List, Optional, Sequence

from domain.models import Assignment, Play, Player, RoutePoint
from sim.ai_decision import OffenseContext, PlayChoice, call_offense
from sim.engine import PlayResult, simulate_play
from sim.statbook import StatBook


@dataclass
class TuningConfig:
    completion_mod: float = 1.0
    pressure_mod: float = 1.0
    int_mod: float = 1.0
    yac_mod: float = 1.0
    rush_block_mod: float = 1.0
    penalty_rate_mod: float = 1.0


TUNING = TuningConfig()


@dataclass
class GameConfig:
    quarter_length: float = 900.0
    quarters: int = 4
    max_plays: int = 130
    kickoff_yardline: float = 25.0


@dataclass
class DriveSummary:
    offense: str
    quarter: int
    plays: int
    yards: float
    duration: float
    start_yardline: float
    end_yardline: float
    result: str


@dataclass
class GameSummary:
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    drives: List[DriveSummary]
    total_plays: int
    time_remaining: float
    winner: Optional[str]
    home_boxscore: Dict[str, Dict[str, Dict[str, float]]]
    away_boxscore: Dict[str, Dict[str, Dict[str, float]]]


@dataclass
class _TeamState:
    name: str
    roster: Dict[str, Player]
    book: StatBook
    score: int = 0


_PASS_ROUTE_PRIMARY = [
    RoutePoint(timestamp=0.0, x=-5.0, y=0.0),
    RoutePoint(timestamp=1.1, x=-2.0, y=8.0),
]
_PASS_ROUTE_SECONDARY = [
    RoutePoint(timestamp=0.0, x=5.0, y=0.0),
    RoutePoint(timestamp=1.3, x=8.0, y=6.0),
]
_SIDELINE_ROUTE = [
    RoutePoint(timestamp=0.0, x=12.0, y=0.0),
    RoutePoint(timestamp=1.2, x=15.0, y=12.0),
]
_RUN_ROUTE = [
    RoutePoint(timestamp=0.0, x=0.0, y=0.0),
    RoutePoint(timestamp=2.0, x=0.0, y=8.0),
]


def simulate_game(
    home_team: str,
    home_roster: Dict[str, Player],
    home_book: StatBook,
    away_team: str,
    away_roster: Dict[str, Player],
    away_book: StatBook,
    *,
    seed: int,
    config: Optional[GameConfig] = None,
) -> GameSummary:
    cfg = config or GameConfig()
    rng = Random(seed)

    teams = [
        _TeamState(name=home_team, roster=home_roster, book=home_book),
        _TeamState(name=away_team, roster=away_roster, book=away_book),
    ]

    offense_idx = rng.choice([0, 1])
    defense_idx = 1 - offense_idx

    total_game_time = cfg.quarter_length * cfg.quarters
    remaining_time = total_game_time

    total_plays = 0
    drives: List[DriveSummary] = []

    next_start_yardline = cfg.kickoff_yardline

    while remaining_time > 0 and total_plays < cfg.max_plays:
        offense = teams[offense_idx]
        defense = teams[defense_idx]

        yardline = _clamp_yardline(next_start_yardline)
        down = 1
        yards_to_first = min(10.0, 100.0 - yardline)
        drive_yards = 0.0
        drive_duration = 0.0
        drive_plays = 0
        drive_result = "CLOCK"
        start_yardline = yardline
        start_quarter = _current_quarter(cfg, remaining_time)

        while remaining_time > 0 and total_plays < cfg.max_plays:
            if down == 4 and yards_to_first > 2.0:
                outcome, time_spent, new_start, change_possession, points = _handle_special_down(
                    yardline, rng
                )
                time_spent = min(time_spent, remaining_time)
                remaining_time -= time_spent
                drive_duration += time_spent
                total_plays += 1
                drive_plays += 1
                drive_result = outcome
                if points:
                    offense.score += points
                next_start_yardline = new_start
                if change_possession:
                    offense_idx, defense_idx = defense_idx, offense_idx
                break

            current_quarter = _current_quarter(cfg, remaining_time)
            play = _select_play(
                offense,
                defense,
                down,
                yards_to_first,
                yardline,
                remaining_time,
                current_quarter,
                rng,
            )
            play_seed = rng.randint(0, 2**31 - 1)
            result = simulate_play(play, offense.roster, defense.roster, seed=play_seed)

            total_plays += 1
            drive_plays += 1

            time_spent = min(_estimate_time_spent(result, rng), remaining_time)
            remaining_time -= time_spent
            drive_duration += time_spent

            _record_events(offense, defense, result)

            drive_yards += result.yards_gained
            yardline = _clamp_yardline(yardline + result.yards_gained)
            yards_to_first = max(0.0, yards_to_first - result.yards_gained)

            if result.interception:
                drive_result = "INT"
                next_start_yardline = _flip_field(yardline)
                offense_idx, defense_idx = defense_idx, offense_idx
                break

            if yardline >= 100.0:
                offense.score += 7
                drive_result = "TD"
                next_start_yardline = cfg.kickoff_yardline
                offense_idx, defense_idx = defense_idx, offense_idx
                kickoff_time = min(6.0, remaining_time)
                remaining_time -= kickoff_time
                drive_duration += kickoff_time
                break

            if yards_to_first <= 0.5:
                down = 1
                yards_to_first = min(10.0, 100.0 - yardline)
            else:
                down += 1
                if down > 4:
                    drive_result = "TURNOVER"
                    next_start_yardline = _flip_field(yardline)
                    offense_idx, defense_idx = defense_idx, offense_idx
                    break

            if remaining_time <= 0:
                drive_result = "CLOCK"
                next_start_yardline = yardline
                break

        drives.append(
            DriveSummary(
                offense=offense.name,
                quarter=start_quarter,
                plays=drive_plays,
                yards=drive_yards,
                duration=drive_duration,
                start_yardline=start_yardline,
                end_yardline=_clamp_yardline(yardline),
                result=drive_result,
            )
        )

        if remaining_time <= 0 or total_plays >= cfg.max_plays:
            break

    home_state, away_state = teams
    winner: Optional[str]
    if home_state.score > away_state.score:
        winner = home_state.name
    elif away_state.score > home_state.score:
        winner = away_state.name
    else:
        winner = None

    return GameSummary(
        home_team=home_state.name,
        away_team=away_state.name,
        home_score=home_state.score,
        away_score=away_state.score,
        drives=drives,
        total_plays=total_plays,
        time_remaining=max(0.0, remaining_time),
        winner=winner,
        home_boxscore=home_state.book.boxscore(),
        away_boxscore=away_state.book.boxscore(),
    )


def _current_quarter(config: GameConfig, remaining_time: float) -> int:
    elapsed = config.quarter_length * config.quarters - remaining_time
    quarter = int(elapsed // config.quarter_length) + 1
    return max(1, min(config.quarters, quarter))


def _estimate_time_spent(result: PlayResult, rng: Random) -> float:
    if result.interception:
        return rng.uniform(8.0, 14.0)
    if result.sack:
        return rng.uniform(18.0, 24.0)
    if result.play_type == "pass" and not result.completed:
        return rng.uniform(6.0, 9.0)
    if result.play_type == "pass" and result.completed:
        return rng.uniform(18.0, 28.0)
    return rng.uniform(20.0, 32.0)


def _handle_special_down(yardline: float, rng: Random) -> tuple[str, float, float, bool, int]:
    if yardline >= 65.0:
        make = rng.random() < 0.84
        if make:
            return "FG", 5.0, 25.0, True, 3
        return "FGMISS", 5.0, _flip_field(yardline), True, 0

    net = 38.0 + rng.uniform(-5.0, 5.0)
    flipped = _flip_field(min(100.0, yardline + net))
    new_start = _clamp_yardline(max(15.0, min(80.0, flipped)))
    return "PUNT", 6.0, new_start, True, 0


def _flip_field(yardline: float) -> float:
    return _clamp_yardline(100.0 - yardline)


def _clamp_yardline(value: float) -> float:
    return max(0.0, min(100.0, value))


def _record_events(offense: _TeamState, defense: _TeamState, result: PlayResult) -> None:
    offense.book.extend(result.events)
    defensive_events = [evt for evt in result.events if evt.team == "defense"]
    if defensive_events:
        defense.book.extend(defensive_events)


def _select_play(
    offense: _TeamState,
    defense: _TeamState,
    down: int,
    yards_to_first: float,
    yardline: float,
    remaining_time: float,
    quarter: int,
    rng: Random,
) -> Play:
    context = OffenseContext(
        down=down,
        yards_to_first=yards_to_first,
        yardline=yardline,
        remaining_time=remaining_time,
        score_diff=offense.score - defense.score,
        quarter=quarter,
    )
    choice: PlayChoice = call_offense(context, rng)
    if choice.category == "run":
        return _build_run_play(offense.roster)
    if choice.category == "sideline_pass":
        return _build_sideline_pass(offense.roster)
    return _build_pass_play(offense.roster)


def _build_pass_play(roster: Dict[str, Player]) -> Play:
    qb = _choose_player(roster, {"QB"})
    wrs = _choose_multiple(roster, {"WR", "TE"}, 2)
    rb = _choose_player(roster, {"RB", "WR", "TE"})
    exclude_ids = {qb.player_id, wrs[0].player_id, wrs[1].player_id, rb.player_id}
    blockers = _choose_multiple(roster, {"OL", "TE", "RB"}, 3, exclude=exclude_ids)

    assignments: List[Assignment] = [
        Assignment(player_id=qb.player_id, role="pass", route=None),
        Assignment(player_id=wrs[0].player_id, role="route", route=list(_PASS_ROUTE_PRIMARY)),
        Assignment(player_id=wrs[1].player_id, role="route", route=list(_PASS_ROUTE_SECONDARY)),
        Assignment(player_id=rb.player_id, role="carry", route=None),
    ]
    for blocker in blockers:
        assignments.append(Assignment(player_id=blocker.player_id, role="block", route=None))

    return Play(
        play_id="auto_pass",
        name="Auto Pass",
        formation="Shotgun",
        personnel="11",
        play_type="offense",
        assignments=assignments,
    )


def _build_sideline_pass(roster: Dict[str, Player]) -> Play:
    qb = _choose_player(roster, {"QB"})
    wr = _choose_player(roster, {"WR", "TE"}, exclude={qb.player_id})
    secondary = _choose_player(roster, {"WR", "TE"}, exclude={qb.player_id, wr.player_id})
    rb = _choose_player(roster, {"RB", "WR", "TE"}, exclude={qb.player_id, wr.player_id, secondary.player_id})
    exclude_ids = {qb.player_id, wr.player_id, secondary.player_id, rb.player_id}
    blockers = _choose_multiple(roster, {"OL", "TE", "RB"}, 3, exclude=exclude_ids)

    assignments: List[Assignment] = [
        Assignment(player_id=qb.player_id, role="pass", route=None),
        Assignment(player_id=wr.player_id, role="route", route=list(_SIDELINE_ROUTE)),
        Assignment(player_id=secondary.player_id, role="route", route=list(_PASS_ROUTE_PRIMARY)),
        Assignment(player_id=rb.player_id, role="carry", route=None),
    ]
    for blocker in blockers:
        assignments.append(Assignment(player_id=blocker.player_id, role="block", route=None))

    return Play(
        play_id="sideline_pass",
        name="Sideline Pass",
        formation="Shotgun",
        personnel="11",
        play_type="offense",
        assignments=assignments,
    )


def _build_run_play(roster: Dict[str, Player]) -> Play:
    qb = _choose_player(roster, {"QB"}, optional=True)
    rb = _choose_player(roster, {"RB", "WR"})
    exclude_ids = {rb.player_id}
    if qb:
        exclude_ids.add(qb.player_id)
    blockers = _choose_multiple(roster, {"OL", "TE", "WR"}, 4, exclude=exclude_ids)

    assignments: List[Assignment] = [
        Assignment(player_id=rb.player_id, role="carry", route=list(_RUN_ROUTE)),
    ]
    if qb:
        assignments.append(Assignment(player_id=qb.player_id, role="block", route=None))
    for blocker in blockers:
        assignments.append(Assignment(player_id=blocker.player_id, role="block", route=None))

    return Play(
        play_id="auto_run",
        name="Auto Run",
        formation="Singleback",
        personnel="12",
        play_type="offense",
        assignments=assignments,
    )


def _choose_player(
    roster: Dict[str, Player],
    positions: Sequence[str],
    *,
    exclude: Optional[Iterable[str]] = None,
    optional: bool = False,
) -> Optional[Player]:
    exclude_set = set(exclude or [])
    for player in roster.values():
        if player.position in positions and player.player_id not in exclude_set:
            return player
    if optional:
        return None
    raise ValueError(f"Roster missing required position from {positions}")


def _choose_multiple(
    roster: Dict[str, Player],
    positions: Sequence[str],
    count: int,
    *,
    exclude: Optional[Iterable[str]] = None,
) -> List[Player]:
    exclude_set = set(exclude or [])
    selected: List[Player] = []
    for player in roster.values():
        if player.player_id in exclude_set:
            continue
        if player.position in positions and player not in selected:
            selected.append(player)
            if len(selected) == count:
                break
    if len(selected) < count:
        raise ValueError(f"Roster missing enough players for positions {positions}")
    return selected






