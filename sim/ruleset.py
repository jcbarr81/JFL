from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict
from random import Random
from typing import Dict, Iterable, List, Optional, Sequence

from sim.special_teams import PenaltyType, apply_penalty, attempt_field_goal
from sim.fatigue import FatigueState, InjuryOutcome, check_injury


@dataclass
class TuningConfig:
    completion_mod: float = 0.65
    pressure_mod: float = 0.045
    sack_distance: float = 0.9
    int_mod: float = 0.19
    yac_mod: float = 0.8
    rush_block_mod: float = 1.2
    penalty_rate_mod: float = 1.0


TUNING = TuningConfig()


from domain.models import Assignment, Play, Player, RoutePoint
from sim.ai_decision import OffenseContext, PlayChoice, call_offense
from sim.engine import PlayResult, simulate_play
from sim.statbook import PlayEvent, StatBook





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
    home_events: List[PlayEvent] = field(default_factory=list)
    away_events: List[PlayEvent] = field(default_factory=list)


@dataclass
class _TeamState:
    name: str
    roster: Dict[str, Player]
    book: StatBook
    score: int = 0
    fatigue: Dict[str, FatigueState] = field(default_factory=dict)
    injuries: Dict[str, "InjuryStatus"] = field(default_factory=dict)

    def fatigue_state(self, player_id: str) -> FatigueState:
        return self.fatigue.setdefault(player_id, FatigueState())

    def recover_between_drives(self, drive_index: int, seconds: float) -> None:
        recovery = max(0.0, seconds * 0.01)
        for player_id in list(self.injuries.keys()):
            status = self.injuries[player_id]
            if status.return_drive is not None and drive_index >= status.return_drive:
                del self.injuries[player_id]
        for state in self.fatigue.values():
            state.apply(0.0, recovery=recovery)

    def apply_fatigue(self, player_id: str, load: float, *, recovery: float = 0.01) -> None:
        if load <= 0 and recovery <= 0:
            return
        state = self.fatigue_state(player_id)
        state.apply(max(0.0, load), recovery=recovery)

    def apply_injury(self, player_id: str, outcome: InjuryOutcome, drive_index: int) -> Optional["InjuryStatus"]:
        if not outcome.injured:
            return None
        severity = outcome.severity or "moderate"
        if severity == "minor":
            status = InjuryStatus(severity="minor", return_drive=drive_index + 1)
        elif severity == "moderate":
            status = InjuryStatus(severity="moderate", return_drive=None)
        else:
            status = InjuryStatus(severity="severe", return_drive=None)
        self.injuries[player_id] = status
        return status

    def is_available(self, player_id: str, drive_index: int) -> bool:
        status = self.injuries.get(player_id)
        if not status:
            return True
        if status.return_drive is not None and drive_index >= status.return_drive:
            del self.injuries[player_id]
            return True
        return False

    def available_players(
        self,
        positions: Sequence[str],
        *,
        exclude: Optional[Iterable[str]] = None,
        drive_index: int,
    ) -> List[Player]:
        exclude_set = set(exclude or [])
        candidates: List[tuple[float, Player]] = []
        for player in self.roster.values():
            if player.position not in positions or player.player_id in exclude_set:
                continue
            if not self.is_available(player.player_id, drive_index):
                continue
            fatigue_value = self.fatigue_state(player.player_id).value
            candidates.append((fatigue_value, player))
        candidates.sort(key=lambda pair: (pair[0], pair[1].player_id))
        return [player for _, player in candidates]


@dataclass
class InjuryStatus:
    severity: str
    return_drive: Optional[int] = None



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

OFFENSE_ROLE_FATIGUE = {
    "pass": 0.08,
    "carry": 0.2,
    "route": 0.14,
    "block": 0.12,
}
DEFENSE_BASE_FATIGUE = 0.1
PRESSURE_FATIGUE_BONUS = 0.05
TACKLE_FATIGUE_BONUS = 0.07
SACK_FATIGUE_BONUS = 0.09
OFFENSE_DRIVE_RECOVERY = 28.0
DEFENSE_DRIVE_RECOVERY = 20.0
BASE_PENALTY_RATE = 0.05
PASS_PENALTY_BONUS = 0.02
RUN_PENALTY_BONUS = 0.01
PRESSURE_PENALTY_BONUS = 0.02
SACK_PENALTY_BONUS = 0.02
FIELD_GOAL_DISTANCE_LIMIT = 58.0
PUNT_NET_MIN = 36.0
PUNT_NET_MAX = 48.0
KICKOFF_MIN_START = 15.0
KICKOFF_MAX_START = 40.0
KICKOFF_TOUCHBACK_THRESHOLD = 20.5
SPECIAL_TEAMS_FATIGUE = 0.06
RETURNER_FATIGUE = 0.08


@dataclass
class SpecialTeamsOutcome:
    result: str
    time_spent: float
    next_start: float
    change_possession: bool
    points: int
    events: List[PlayEvent]


@dataclass
class KickoffSummary:
    start_yardline: float
    time_spent: float
    events: List[PlayEvent]


@dataclass(frozen=True)
class PenaltyDecision:
    team: str
    penalty: PenaltyType


@dataclass
class PenaltyResolution:
    applied: bool
    yardline: float
    yards_to_first: float
    down: int
    drive_yard_adjustment: float
    repeat_down: bool
    force_first_down: bool


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

    event_log: Dict[str, List[PlayEvent]] = {home_team: [], away_team: []}

    offense_idx = rng.choice([0, 1])
    defense_idx = 1 - offense_idx

    total_game_time = cfg.quarter_length * cfg.quarters
    remaining_time = total_game_time

    total_plays = 0
    drives: List[DriveSummary] = []

    next_start_yardline = cfg.kickoff_yardline
    drive_index = 0

    while remaining_time > 0 and total_plays < cfg.max_plays:
        drive_index += 1

        offense = teams[offense_idx]
        defense = teams[defense_idx]

        offense.recover_between_drives(drive_index, OFFENSE_DRIVE_RECOVERY)
        defense.recover_between_drives(drive_index, DEFENSE_DRIVE_RECOVERY)

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
            if down == 4:
                score_diff = offense.score - defense.score
                should_attempt_special = (
                    yards_to_first > 2.0
                    or yardline >= 55.0
                    or score_diff < 0
                    or remaining_time < 120.0
                    or (yards_to_first > 1.0 and yardline >= 45.0)
                )
                if should_attempt_special:
                    special = _handle_special_down(
                        offense,
                        defense,
                        yardline,
                        rng,
                        drive_index,
                    )
                    time_spent = min(special.time_spent, remaining_time)
                    remaining_time -= time_spent
                    drive_duration += time_spent
                    total_plays += 1
                    drive_plays += 1
                    drive_result = special.result
                    if special.points:
                        offense.score += special.points
                        _record_special_events(offense, defense, special.events, event_log)
                        kickoff = _execute_kickoff(offense, defense, rng, drive_index)
                        kick_time = min(kickoff.time_spent, remaining_time)
                        remaining_time -= kick_time
                        drive_duration += kick_time
                        _record_special_events(offense, defense, kickoff.events, event_log)
                        offense_idx, defense_idx = defense_idx, offense_idx
                        next_start_yardline = kickoff.start_yardline
                    else:
                        _record_special_events(offense, defense, special.events, event_log)
                        next_start_yardline = special.next_start
                        if special.change_possession:
                            offense_idx, defense_idx = defense_idx, offense_idx
                    break

            current_quarter = _current_quarter(cfg, remaining_time)
            pre_yardline = yardline
            pre_down = down
            pre_yards_to_first = yards_to_first
            play = _select_play(
                offense,
                defense,
                down,
                yards_to_first,
                yardline,
                remaining_time,
                current_quarter,
                drive_index,
                rng,
            )

            defense_personnel = _select_defensive_unit(defense, drive_index)
            fatigue_modifiers = _fatigue_modifiers_for_play(play, offense, defense, defense_personnel)

            play_seed = rng.randint(0, 2**31 - 1)
            result = simulate_play(
                play,
                offense.roster,
                defense_personnel,
                seed=play_seed,
                fatigue_modifiers=fatigue_modifiers,
            )

            total_plays += 1
            drive_plays += 1

            time_spent = min(_estimate_time_spent(result, rng), remaining_time)
            remaining_time -= time_spent
            drive_duration += time_spent

            _apply_play_consequences(
                offense,
                defense,
                play,
                result,
                defense_personnel,
                drive_index,
                rng,
            )

            drive_yards += result.yards_gained
            yardline = _clamp_yardline(yardline + result.yards_gained)
            yards_to_first = max(0.0, yards_to_first - result.yards_gained)

            penalty_resolution = _maybe_apply_penalty(
                offense,
                defense,
                result,
                pre_yardline,
                yardline,
                pre_down,
                down,
                pre_yards_to_first,
                yards_to_first,
                rng,
            )
            if penalty_resolution.applied:
                yardline = penalty_resolution.yardline
                yards_to_first = penalty_resolution.yards_to_first
                down = penalty_resolution.down
                drive_yards += penalty_resolution.drive_yard_adjustment
                repeat_down = penalty_resolution.repeat_down
                force_first_down = penalty_resolution.force_first_down
            else:
                repeat_down = False
                force_first_down = False

            _record_events(offense, defense, result, event_log)

            if result.interception:
                drive_result = "INT"
                next_start_yardline = _flip_field(yardline)
                offense_idx, defense_idx = defense_idx, offense_idx
                break

            if yardline >= 100.0:
                offense.score += 7
                drive_result = "TD"
                kickoff = _execute_kickoff(offense, defense, rng, drive_index)
                _record_special_events(offense, defense, kickoff.events, event_log)
                kick_time = min(kickoff.time_spent, remaining_time)
                remaining_time -= kick_time
                drive_duration += kick_time
                offense_idx, defense_idx = defense_idx, offense_idx
                next_start_yardline = kickoff.start_yardline
                break

            if yards_to_first <= 0.5:
                down = 1
                yards_to_first = min(10.0, 100.0 - yardline)
            elif force_first_down:
                down = 1
                yards_to_first = min(10.0, 100.0 - yardline)
            else:
                if not repeat_down:
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
    home_events = list(event_log.get(home_state.name, []))
    away_events = list(event_log.get(away_state.name, []))
    if home_state.score > away_state.score:
        winner: Optional[str] = home_state.name
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
        home_events=home_events,
        away_events=away_events,
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


def _handle_special_down(
    offense: _TeamState,
    defense: _TeamState,
    yardline: float,
    rng: Random,
    drive_index: int,
) -> SpecialTeamsOutcome:
    distance = max(20.0, 100.0 - yardline + 17.0)
    kicker = _choose_player(
        offense,
        ["K"],
        drive_index=drive_index,
        fallback=["P", "QB"],
        optional=True,
    )
    if distance <= FIELD_GOAL_DISTANCE_LIMIT:
        return _field_goal_attempt(
            offense,
            defense,
            yardline,
            distance,
            kicker,
            rng,
            drive_index,
        )
    return _punt_ball(offense, defense, yardline, rng, drive_index)



def _field_goal_attempt(
    offense: _TeamState,
    defense: _TeamState,
    yardline: float,
    distance: float,
    kicker: Optional[Player],
    rng: Random,
    drive_index: int,
) -> SpecialTeamsOutcome:
    kicker_rating = kicker.attributes.accuracy if kicker else 70
    attempt = attempt_field_goal(yardline, kicker_rating, rng)
    events: List[PlayEvent] = [
        PlayEvent(
            type="field_goal_attempt",
            timestamp=0.0,
            team="offense",
            player_id=kicker.player_id if kicker else None,
            yards=distance,
            metadata={"distance": distance, "made": attempt.made, "kick_yards": attempt.yards},
        )
    ]
    if kicker:
        offense.apply_fatigue(kicker.player_id, SPECIAL_TEAMS_FATIGUE)
    time_spent = rng.uniform(5.0, 7.0)
    if attempt.made:
        return SpecialTeamsOutcome("FG", time_spent, yardline, True, 3, events)
    miss_start = _clamp_yardline(max(20.0, 100.0 - yardline))
    return SpecialTeamsOutcome("FGMISS", time_spent, miss_start, True, 0, events)


def _punt_ball(
    offense: _TeamState,
    defense: _TeamState,
    yardline: float,
    rng: Random,
    drive_index: int,
) -> SpecialTeamsOutcome:
    punter = _choose_player(
        offense,
        ["P"],
        drive_index=drive_index,
        fallback=["K", "QB"],
        optional=True,
    )
    strength = punter.attributes.strength if punter else 78
    net = rng.uniform(PUNT_NET_MIN, PUNT_NET_MAX) + (strength - 80) * 0.15
    net = max(PUNT_NET_MIN - 2.0, min(PUNT_NET_MAX + 4.0, net))
    landing = min(100.0, yardline + net)
    touchback = landing >= 100.0
    events: List[PlayEvent] = [
        PlayEvent(
            type="punt",
            timestamp=0.0,
            team="offense",
            player_id=punter.player_id if punter else None,
            yards=net,
            metadata={"landing": landing, "touchback": touchback},
        )
    ]
    if punter:
        offense.apply_fatigue(punter.player_id, SPECIAL_TEAMS_FATIGUE)
    if touchback:
        next_start = 25.0
    else:
        base_start = max(1.0, 100.0 - landing)
        returner = _choose_player(
            defense,
            ["WR", "RB", "CB"],
            drive_index=drive_index,
            fallback=["S", "LB"],
            optional=True,
        )
        return_gain = 0.0
        if returner:
            defense.apply_fatigue(returner.player_id, RETURNER_FATIGUE)
            return_gain = max(0.0, rng.uniform(0.0, 12.0) + (returner.attributes.speed - 85) * 0.05)
            next_start = max(1.0, min(50.0, base_start + return_gain))
            return_yards = max(0.0, next_start - base_start)
            events.append(
                PlayEvent(
                    type="punt_return",
                    timestamp=0.0,
                    team="defense",
                    player_id=returner.player_id,
                    yards=return_yards,
                    metadata={"end": next_start},
                )
            )
        else:
            next_start = base_start
    time_spent = rng.uniform(6.0, 8.0)
    return SpecialTeamsOutcome("PUNT", time_spent, next_start, True, 0, events)


def _execute_kickoff(
    kicking: _TeamState,
    receiving: _TeamState,
    rng: Random,
    drive_index: int,
) -> KickoffSummary:
    kicker = _choose_player(
        kicking,
        ["K"],
        drive_index=drive_index,
        fallback=["P", "QB"],
        optional=True,
    )
    strength = kicker.attributes.strength if kicker else 80
    base_start = rng.gauss(26.0, 4.0) - (strength - 80) * 0.05
    returner = _choose_player(
        receiving,
        ["WR", "RB", "CB"],
        drive_index=drive_index,
        fallback=["S", "LB"],
        optional=True,
    )
    if returner:
        base_start += max(-2.0, (returner.attributes.speed - 85) * 0.06)
    start_yard = max(KICKOFF_MIN_START, min(KICKOFF_MAX_START, base_start))
    touchback = start_yard <= KICKOFF_TOUCHBACK_THRESHOLD
    events: List[PlayEvent] = [
        PlayEvent(
            type="kickoff",
            timestamp=0.0,
            team="offense",
            player_id=kicker.player_id if kicker else None,
            yards=start_yard,
            metadata={"start": start_yard, "touchback": touchback},
        )
    ]
    if kicker:
        kicking.apply_fatigue(kicker.player_id, SPECIAL_TEAMS_FATIGUE)
    if touchback:
        start_yard = 25.0
    else:
        if returner:
            receiving.apply_fatigue(returner.player_id, RETURNER_FATIGUE)
            return_gain = max(0.0, start_yard - 25.0)
            events.append(
                PlayEvent(
                    type="kick_return",
                    timestamp=0.0,
                    team="defense",
                    player_id=returner.player_id,
                    yards=return_gain,
                    metadata={"end": start_yard},
                )
            )
    time_spent = rng.uniform(6.0, 9.0)
    return KickoffSummary(start_yard, time_spent, events)


def _flip_field(yardline: float) -> float:
    return _clamp_yardline(100.0 - yardline)


def _clamp_yardline(value: float) -> float:
    return max(0.0, min(100.0, value))


def _record_special_events(
    offense: _TeamState,
    defense: _TeamState,
    events: Iterable[PlayEvent],
    event_log: Dict[str, List[PlayEvent]],
) -> None:
    if not events:
        return
    offense_events = [evt for evt in events if evt.team == "offense"]
    defense_events = [evt for evt in events if evt.team == "defense"]
    if offense_events:
        offense.book.extend(offense_events)
        event_log.setdefault(offense.name, []).extend(offense_events)
    if defense_events:
        defense.book.extend(defense_events)
        event_log.setdefault(defense.name, []).extend(defense_events)


def _record_events(
    offense: _TeamState,
    defense: _TeamState,
    result: PlayResult,
    event_log: Dict[str, List[PlayEvent]],
) -> None:
    offense.book.extend(result.events)
    event_log.setdefault(offense.name, []).extend(result.events)
    defensive_events = [evt for evt in result.events if evt.team == "defense"]
    if defensive_events:
        defense.book.extend(defensive_events)
        event_log.setdefault(defense.name, []).extend(defensive_events)


def _select_play(
    offense: _TeamState,
    defense: _TeamState,
    down: int,
    yards_to_first: float,
    yardline: float,
    remaining_time: float,
    quarter: int,
    drive_index: int,
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
        return _build_run_play(offense, drive_index)
    if choice.category == "sideline_pass":
        return _build_sideline_pass(offense, drive_index)
    return _build_pass_play(offense, drive_index)


def _build_pass_play(team: _TeamState, drive_index: int) -> Play:
    qb = _choose_player(team, ["QB"], drive_index=drive_index, fallback=["WR", "RB", "TE"])
    wrs = _choose_multiple(team, ["WR", "TE"], 2, drive_index=drive_index, exclude={qb.player_id})
    rb = _choose_player(
        team,
        ["RB", "WR", "TE"],
        drive_index=drive_index,
        exclude={qb.player_id, wrs[0].player_id, wrs[1].player_id},
    )
    exclude_ids = {qb.player_id, wrs[0].player_id, wrs[1].player_id, rb.player_id}
    blockers = _choose_multiple(team, ["OL", "TE", "RB"], 3, drive_index=drive_index, exclude=exclude_ids)

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


def _build_sideline_pass(team: _TeamState, drive_index: int) -> Play:
    qb = _choose_player(team, ["QB"], drive_index=drive_index, fallback=["WR", "RB", "TE"])
    wr = _choose_player(team, ["WR", "TE"], drive_index=drive_index, exclude={qb.player_id})
    secondary = _choose_player(
        team,
        ["WR", "TE"],
        drive_index=drive_index,
        exclude={qb.player_id, wr.player_id},
    )
    rb = _choose_player(
        team,
        ["RB", "WR", "TE"],
        drive_index=drive_index,
        exclude={qb.player_id, wr.player_id, secondary.player_id},
    )
    exclude_ids = {qb.player_id, wr.player_id, secondary.player_id, rb.player_id}
    blockers = _choose_multiple(team, ["OL", "TE", "RB"], 3, drive_index=drive_index, exclude=exclude_ids)

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


def _build_run_play(team: _TeamState, drive_index: int) -> Play:
    qb = _choose_player(team, ["QB"], drive_index=drive_index, fallback=["WR", "RB"], optional=True)
    exclude_ids: set[str] = set()
    if qb:
        exclude_ids.add(qb.player_id)
    rb = _choose_player(team, ["RB", "WR"], drive_index=drive_index, exclude=exclude_ids)
    exclude_ids.add(rb.player_id)
    blockers = _choose_multiple(team, ["OL", "TE", "WR"], 4, drive_index=drive_index, exclude=exclude_ids)

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
    team: _TeamState,
    positions: Sequence[str],
    *,
    drive_index: int,
    exclude: Optional[Iterable[str]] = None,
    fallback: Optional[Sequence[str]] = None,
    optional: bool = False,
) -> Optional[Player]:
    exclude_set = set(exclude or [])
    candidates = team.available_players(positions, exclude=exclude_set, drive_index=drive_index)
    if candidates:
        return candidates[0]
    if fallback:
        fallback_candidates = team.available_players(fallback, exclude=exclude_set, drive_index=drive_index)
        if fallback_candidates:
            return fallback_candidates[0]
    if optional:
        return None
    for player in team.roster.values():
        if player.player_id in exclude_set:
            continue
        if team.is_available(player.player_id, drive_index):
            return player
    for player in team.roster.values():
        if player.player_id not in exclude_set:
            return player
    raise ValueError(f"Roster missing required position from {positions}")


def _choose_multiple(
    team: _TeamState,
    positions: Sequence[str],
    count: int,
    *,
    drive_index: int,
    exclude: Optional[Iterable[str]] = None,
) -> List[Player]:
    exclude_set = set(exclude or [])
    selected: List[Player] = []
    for _ in range(count):
        player = _choose_player(team, positions, drive_index=drive_index, exclude=exclude_set)
        if not player:
            break
        selected.append(player)
        exclude_set.add(player.player_id)
    if len(selected) < count:
        raise ValueError(f"Roster missing enough players for positions {positions}")
    return selected


def _select_defensive_unit(team: _TeamState, drive_index: int) -> Dict[str, Player]:
    template = [
        ["DL"],
        ["DL"],
        ["DL"],
        ["DL"],
        ["LB"],
        ["LB"],
        ["LB"],
        ["CB"],
        ["CB"],
        ["S"],
        ["S"],
    ]
    unit: Dict[str, Player] = {}
    exclude: set[str] = set()
    for positions in template:
        try:
            player = _choose_player(team, positions, drive_index=drive_index, exclude=exclude)
        except ValueError:
            try:
                player = _choose_player(team, ["LB", "DL", "CB", "S"], drive_index=drive_index, exclude=exclude)
            except ValueError:
                player = None
        if player is None:
            continue
        unit[player.player_id] = player
        exclude.add(player.player_id)
    if len(unit) < 11:
        extras = team.available_players(
            ["DL", "LB", "CB", "S", "TE", "WR"],
            exclude=exclude,
            drive_index=drive_index,
        )
        for player in extras:
            if player.player_id in unit:
                continue
            unit[player.player_id] = player
            if len(unit) == 11:
                break
    if len(unit) < 11:
        raise ValueError("Team lacks enough healthy defenders")
    selected: Dict[str, Player] = {}
    for player_id, player in unit.items():
        selected[player_id] = player
        if len(selected) == 11:
            break
    return selected


def _fatigue_modifiers_for_play(
    play: Play,
    offense: _TeamState,
    defense: _TeamState,
    defense_personnel: Dict[str, Player],
) -> Dict[str, float]:
    modifiers: Dict[str, float] = {}
    for assignment in play.assignments:
        modifiers[assignment.player_id] = offense.fatigue_state(assignment.player_id).multiplier()
    for player_id in defense_personnel:
        modifiers[player_id] = defense.fatigue_state(player_id).multiplier()
    return modifiers


def _apply_play_consequences(
    offense: _TeamState,
    defense: _TeamState,
    play: Play,
    result: PlayResult,
    defense_personnel: Dict[str, Player],
    drive_index: int,
    rng: Random,
) -> None:
    duration_factor = 0.9 + result.duration / 8.0
    for assignment in play.assignments:
        load = OFFENSE_ROLE_FATIGUE.get(assignment.role, 0.1) * duration_factor
        offense.apply_fatigue(assignment.player_id, load)

    adjustments = _defensive_load_adjustments(result.events)
    base_load = DEFENSE_BASE_FATIGUE * duration_factor
    for player_id in defense_personnel:
        load = base_load + adjustments.get(player_id, 0.0)
        defense.apply_fatigue(player_id, load)

    injury_events: List[PlayEvent] = []
    for event in result.events:
        if event.type not in {"tackle", "sack"}:
            continue
        metadata = event.metadata or {}
        runner_id = metadata.get("runner_id") or event.target_id
        if runner_id and runner_id in offense.roster:
            injury_event = _maybe_trigger_injury(
                offense,
                runner_id,
                event,
                drive_index,
                rng,
                team_label="offense",
            )
            if injury_event:
                injury_events.append(injury_event)
        tackler_id = event.player_id
        if tackler_id and tackler_id in defense.roster:
            injury_event = _maybe_trigger_injury(
                defense,
                tackler_id,
                event,
                drive_index,
                rng,
                team_label="defense",
            )
            if injury_event:
                injury_events.append(injury_event)
    if injury_events:
        result.events.extend(injury_events)


def _defensive_load_adjustments(events: Iterable[PlayEvent]) -> Dict[str, float]:
    adjustments: Dict[str, float] = defaultdict(float)
    for event in events:
        if event.team != "defense" or not event.player_id:
            continue
        if event.type == "pressure":
            adjustments[event.player_id] += PRESSURE_FATIGUE_BONUS
        elif event.type == "sack":
            adjustments[event.player_id] += SACK_FATIGUE_BONUS
        elif event.type == "tackle":
            adjustments[event.player_id] += TACKLE_FATIGUE_BONUS
    return adjustments



def _draw_penalty(result: PlayResult, rng: Random) -> Optional[PenaltyDecision]:
    base = BASE_PENALTY_RATE * TUNING.penalty_rate_mod
    if result.play_type == "pass":
        base += PASS_PENALTY_BONUS
    elif result.play_type == "run":
        base += RUN_PENALTY_BONUS
    if result.pressure:
        base += PRESSURE_PENALTY_BONUS
    if result.sack:
        base += SACK_PENALTY_BONUS
    base = min(0.35, base)
    if rng.random() >= base:
        return None
    roll = rng.random()
    if roll < 0.45:
        return PenaltyDecision(team="offense", penalty=PenaltyType.HOLDING)
    if roll < 0.75:
        return PenaltyDecision(team="defense", penalty=PenaltyType.OFFSIDES)
    return PenaltyDecision(team="defense", penalty=PenaltyType.DPI)


def _maybe_apply_penalty(
    offense: _TeamState,
    defense: _TeamState,
    result: PlayResult,
    pre_yardline: float,
    yardline: float,
    pre_down: int,
    down: int,
    pre_yards_to_first: float,
    yards_to_first: float,
    rng: Random,
) -> PenaltyResolution:
    decision = _draw_penalty(result, rng)
    if not decision:
        return PenaltyResolution(False, yardline, yards_to_first, down, 0.0, False, False)

    penalty = apply_penalty(decision.penalty)
    if not penalty.accepted:
        return PenaltyResolution(False, yardline, yards_to_first, down, 0.0, False, False)

    yards_adjustment = 0.0
    repeat_down = False
    force_first_down = False

    if decision.team == "offense":
        new_yardline = _clamp_yardline(max(0.0, pre_yardline - penalty.yards))
        yards_adjustment = new_yardline - yardline
        new_yards_to_first = min(10.0, 100.0 - new_yardline)
        new_down = pre_down
        repeat_down = True
        result.events.append(
            PlayEvent(
                type="penalty",
                timestamp=result.duration,
                team="offense",
                player_id=None,
                yards=-penalty.yards,
                metadata={
                    "penalty": decision.penalty.name.lower(),
                    "accepted": True,
                    "automatic_first": penalty.automatic_first,
                },
            )
        )
    else:
        new_yardline = _clamp_yardline(yardline + penalty.yards)
        yards_adjustment = new_yardline - yardline
        if penalty.automatic_first:
            new_down = 1
            force_first_down = True
            new_yards_to_first = min(10.0, 100.0 - new_yardline)
        else:
            new_down = pre_down
            repeat_down = True
            new_yards_to_first = max(0.5, pre_yards_to_first - penalty.yards)
        result.events.append(
            PlayEvent(
                type="penalty",
                timestamp=result.duration,
                team="defense",
                player_id=None,
                yards=penalty.yards,
                metadata={
                    "penalty": decision.penalty.name.lower(),
                    "accepted": True,
                    "automatic_first": penalty.automatic_first,
                },
            )
        )
        if result.interception and decision.penalty != PenaltyType.HOLDING:
            result.interception = False

    return PenaltyResolution(
        True,
        new_yardline,
        new_yards_to_first,
        new_down,
        yards_adjustment,
        repeat_down,
        force_first_down,
    )


def _impact_from_event(event: PlayEvent, rng: Random) -> float:
    metadata = event.metadata or {}
    yards_component = abs(event.yards) * 0.004 if event.yards else 0.0
    base = 0.02 + min(0.06, yards_component)
    if event.type == "sack":
        base += 0.02
    play_type = metadata.get("play_type")
    if play_type == "run":
        base += 0.01
    if play_type == "turnover":
        base += 0.015
    base += rng.uniform(-0.005, 0.005)
    return max(0.005, min(0.12, base))


def _maybe_trigger_injury(
    team: _TeamState,
    player_id: str,
    event: PlayEvent,
    drive_index: int,
    rng: Random,
    *,
    team_label: str,
) -> Optional[PlayEvent]:
    player = team.roster.get(player_id)
    if not player:
        return None
    impact = _impact_from_event(event, rng)
    outcome = check_injury(rng, impact=impact, attributes=player.attributes)
    status = team.apply_injury(player_id, outcome, drive_index)
    if not status:
        return None
    return _injury_event(team_label, player_id, event.timestamp, status.severity)


def _injury_event(team: str, player_id: str, timestamp: float, severity: str) -> PlayEvent:
    return PlayEvent(
        type="injury",
        timestamp=timestamp,
        team=team,
        player_id=player_id,
        metadata={"severity": severity},
    )




