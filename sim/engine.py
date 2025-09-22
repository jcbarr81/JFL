from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set

from domain.models import Assignment, Attributes, Play, Player, RoutePoint
from sim.statbook import PlayEvent

TICK_RATE = 20.0
DT = 1.0 / TICK_RATE
MAX_ACCEL = 7.5  # yards / second^2
FATIGUE_DECAY = 0.04  # per second
BALL_BASE_SPEED = 22.0  # yards / second
SACK_LOSS = -1.5


@dataclass
class PlayResult:
    play_type: str
    yards_gained: float
    air_yards: float
    yac: float
    duration: float
    pressure: bool
    sack: bool
    interception: bool
    completed: bool
    events: List[PlayEvent]


@dataclass
class _Entity:
    player: Player
    role: str
    team: str
    route: List[RoutePoint]
    position: List[float]
    velocity: List[float]
    base_speed: float

    def copy(self) -> "_Entity":
        return _Entity(
            player=self.player,
            role=self.role,
            team=self.team,
            route=list(self.route),
            position=list(self.position),
            velocity=list(self.velocity),
            base_speed=self.base_speed,
        )


@dataclass
class _BallState:
    owner_id: Optional[str]
    position: List[float]
    velocity: List[float]
    in_air: bool
    target_owner_id: Optional[str] = None
    arrive_time: Optional[float] = None
    release_time: Optional[float] = None


def simulate_play(
    play: Play,
    offense_roster: Dict[str, Player],
    defense_roster: Dict[str, Player],
    *,
    seed: int,
    duration: float = 8.0,
    tick_rate: float = TICK_RATE,
    fatigue_modifiers: Optional[Dict[str, float]] = None,
    pressure_bonus: float = 1.0,
) -> PlayResult:
    rng = _SeededRandom(seed)
    modifiers = fatigue_modifiers or {}
    from sim.ruleset import TUNING
    globals()["TUNING"] = TUNING
    pressure_factor = max(0.25, min(2.5, pressure_bonus))

    offenses = _initialise_offense_entities(play, offense_roster, modifiers)
    defenses = _initialise_defense_entities(defense_roster, modifiers)

    qb_entity = _select_qb(offenses)
    primary_carrier = qb_entity or _find_primary_carrier(offenses)

    carrier_id = primary_carrier.player.player_id if primary_carrier else None
    ball_position = list(primary_carrier.position) if primary_carrier else [0.0, 0.0]
    ball = _BallState(owner_id=carrier_id, position=ball_position, velocity=[0.0, 0.0], in_air=False)

    events: List[PlayEvent] = []
    events.append(PlayEvent(type="snap", timestamp=0.0, team="offense", player_id=carrier_id))

    rush_attempt_logged = False
    if primary_carrier and primary_carrier.role == "carry" and qb_entity is None:
        events.append(
            PlayEvent(
                type="rush_attempt",
                timestamp=0.0,
                team="offense",
                player_id=primary_carrier.player.player_id,
            )
        )
        rush_attempt_logged = True

    pass_target_assignment = _find_primary_receiver(play)
    pass_target_entity = (
        offenses.get(pass_target_assignment.player_id) if pass_target_assignment else None
    )

    pass_release_time = _sample_pass_release(qb_entity, rng) if qb_entity else None

    released = False
    attempt_logged = False
    completion_logged = False
    pressure = False
    sack = False
    interception = False
    completed = False
    air_yards = 0.0
    yac = 0.0
    yards_gained = 0.0

    total_ticks = int(duration * tick_rate)
    pressured_defenders: Set[str] = set()
    passer_id = qb_entity.player.player_id if qb_entity else None
    runner_id = carrier_id
    receiver_id: Optional[str] = None

    for tick in range(total_ticks):
        time_elapsed = tick * DT
        fatigue = max(0.5, 1 - FATIGUE_DECAY * time_elapsed)

        for entity in offenses.values():
            _advance_entity(entity, time_elapsed, DT, fatigue)
        for entity in defenses.values():
            target = _defense_target_position(ball, entity, offenses, defenses)
            _advance_entity(entity, time_elapsed, DT, fatigue, override_target=target)

        if qb_entity:
            pressure_distance = max(0.02, TUNING.pressure_mod / pressure_factor)
            sack_distance = max(0.5, TUNING.sack_distance / pressure_factor)
            for defender in defenses.values():
                distance = _distance(defender.position, qb_entity.position)
                if distance < pressure_distance and defender.player.player_id not in pressured_defenders:
                    pressure = True
                    pressured_defenders.add(defender.player.player_id)
                    events.append(
                        PlayEvent(
                            type="pressure",
                            timestamp=time_elapsed,
                            team="defense",
                            player_id=defender.player.player_id,
                            target_id=passer_id,
                            metadata={"passer_id": passer_id, "defender_id": defender.player.player_id},
                        )
                    )
                if distance < sack_distance and not released:
                    sack = True
                    pressure = True
                    if qb_entity and not attempt_logged:
                        events.append(
                            PlayEvent(
                                type="pass_attempt",
                                timestamp=time_elapsed,
                                team="offense",
                                player_id=passer_id,
                                target_id=pass_target_entity.player.player_id if pass_target_entity else None,
                            )
                        )
                        attempt_logged = True
                    events.append(
                        PlayEvent(
                            type="sack",
                            timestamp=time_elapsed,
                            team="defense",
                            player_id=defender.player.player_id,
                            target_id=passer_id,
                            yards=SACK_LOSS,
                            metadata={"qb_id": passer_id, "yards_lost": SACK_LOSS},
                        )
                    )
                    events.append(
                        PlayEvent(
                            type="tackle",
                            timestamp=time_elapsed,
                            team="defense",
                            player_id=defender.player.player_id,
                            target_id=passer_id,
                            yards=SACK_LOSS,
                            metadata={
                                "play_type": "pass",
                                "passer_id": passer_id,
                                "runner_id": passer_id,
                                "receiver_id": None,
                                "air_yards": 0.0,
                                "yac": 0.0,
                            },
                        )
                    )
                    return _finalize_play(
                        events,
                        timestamp=time_elapsed,
                        play_type="pass",
                        yards_gained=SACK_LOSS,
                        air_yards=0.0,
                        yac=0.0,
                        duration=time_elapsed,
                        pressure=pressure,
                        sack=True,
                        interception=False,
                        completed=False,
                        passer_id=passer_id,
                        runner_id=passer_id,
                        receiver_id=None,
                    )

        if not released and qb_entity and pass_target_entity and pass_release_time is not None and time_elapsed >= pass_release_time:
            released = True
            if not attempt_logged:
                events.append(
                    PlayEvent(
                        type="pass_attempt",
                        timestamp=time_elapsed,
                        team="offense",
                        player_id=passer_id,
                        target_id=pass_target_entity.player.player_id,
                    )
                )
                attempt_logged = True
            ball.owner_id = None
            ball.in_air = True
            ball.release_time = time_elapsed
            ball.target_owner_id = pass_target_entity.player.player_id
            qb_pos = list(qb_entity.position)
            target_future = _predict_route_position(pass_target_entity, time_elapsed, pass_release_time, rng)
            air_vector = [target_future[0] - qb_pos[0], target_future[1] - qb_pos[1]]
            distance = _length(air_vector)
            throw_speed = BALL_BASE_SPEED + (qb_entity.player.attributes.throwing_power - 70) * 0.25
            throw_speed = max(15.0, min(throw_speed, 35.0))
            flight_time = distance / throw_speed if throw_speed else 0.0
            ball.arrive_time = time_elapsed + flight_time
            accuracy_offset = rng.normal(0.0, _accuracy_std(qb_entity.player.attributes.accuracy))
            target_future[0] += accuracy_offset
            norm = _length(air_vector)
            if norm > 0:
                ball.velocity = [
                    (target_future[0] - qb_pos[0]) / max(flight_time, DT),
                    (target_future[1] - qb_pos[1]) / max(flight_time, DT),
                ]
            else:
                ball.velocity = [0.0, throw_speed]
            ball.position = qb_pos[:]
            air_yards = target_future[1] - qb_pos[1]

        if ball.in_air:
            ball.position[0] += ball.velocity[0] * DT
            ball.position[1] += ball.velocity[1] * DT

            if ball.arrive_time is not None and time_elapsed >= ball.arrive_time:
                target_entity = offenses.get(ball.target_owner_id) if ball.target_owner_id else None
                nearest_defender = _nearest_defender(ball.position, defenses.values())
                completed, interception = _resolve_catch(
                    qb_entity,
                    target_entity,
                    nearest_defender,
                    rng,
                )
                ball.in_air = False
                if completed and target_entity:
                    receiver_id = target_entity.player.player_id
                    runner_id = receiver_id
                    events.append(
                        PlayEvent(
                            type="pass_completion",
                            timestamp=time_elapsed,
                            team="offense",
                            player_id=receiver_id,
                            target_id=passer_id,
                            yards=air_yards,
                            metadata={
                                "passer_id": passer_id,
                                "receiver_id": receiver_id,
                                "air_yards": air_yards,
                            },
                        )
                    )
                    completion_logged = True
                    completed = True
                    ball.owner_id = receiver_id
                    ball.position = list(target_entity.position)
                elif interception and nearest_defender:
                    defender_id = nearest_defender.player.player_id
                    events.append(
                        PlayEvent(
                            type="interception",
                            timestamp=time_elapsed,
                            team="defense",
                            player_id=defender_id,
                            target_id=passer_id,
                            metadata={
                                "passer_id": passer_id,
                                "defender_id": defender_id,
                            },
                        )
                    )
                    return _finalize_play(
                        events,
                        timestamp=time_elapsed,
                        play_type="pass",
                        yards_gained=0.0,
                        air_yards=max(0.0, air_yards),
                        yac=0.0,
                        duration=time_elapsed,
                        pressure=pressure,
                        sack=False,
                        interception=True,
                        completed=False,
                        passer_id=passer_id,
                        runner_id=None,
                        receiver_id=None,
                    )
                else:
                    events.append(
                        PlayEvent(
                            type="pass_incomplete",
                            timestamp=time_elapsed,
                            team="offense",
                            player_id=passer_id,
                            target_id=pass_target_entity.player.player_id if pass_target_entity else None,
                        )
                    )
                    return _finalize_play(
                        events,
                        timestamp=time_elapsed,
                        play_type="pass",
                        yards_gained=0.0,
                        air_yards=max(0.0, air_yards),
                        yac=0.0,
                        duration=time_elapsed,
                        pressure=pressure,
                        sack=False,
                        interception=False,
                        completed=False,
                        passer_id=passer_id,
                        runner_id=None,
                        receiver_id=None,
                    )

        if ball.owner_id:
            owner_entity = offenses.get(ball.owner_id) or defenses.get(ball.owner_id)
            if owner_entity:
                ball.position = list(owner_entity.position)

            if owner_entity and owner_entity.team == "offense":
                for defender in defenses.values():
                    if _distance(defender.position, owner_entity.position) < 1.5:
                        if owner_entity.role == "carry" and qb_entity is None and not completion_logged and not rush_attempt_logged:
                            events.append(
                                PlayEvent(
                                    type="rush_attempt",
                                    timestamp=time_elapsed,
                                    team="offense",
                                    player_id=owner_entity.player.player_id,
                                )
                            )
                            rush_attempt_logged = True
                        if _attempt_tackle(defender.player.attributes, owner_entity.player.attributes, rng):
                            yards_gained = _yard_line(owner_entity.position[1])
                            yac = max(0.0, yards_gained - max(0.0, air_yards)) if released else 0.0
                            if released:
                                yac = max(0.0, min(100.0, yac * TUNING.yac_mod))
                                yards_gained = max(0.0, min(100.0, max(0.0, air_yards) + yac))
                            else:
                                yards_gained = max(0.0, min(100.0, yards_gained * TUNING.rush_block_mod))
                            events.append(
                                PlayEvent(
                                    type="tackle",
                                    timestamp=time_elapsed,
                                    team="defense",
                                    player_id=defender.player.player_id,
                                    target_id=owner_entity.player.player_id,
                                    yards=yards_gained,
                                    metadata={
                                        "play_type": "pass" if released else "run",
                                        "passer_id": passer_id,
                                        "runner_id": owner_entity.player.player_id,
                                        "receiver_id": owner_entity.player.player_id if released else None,
                                        "air_yards": max(0.0, air_yards),
                                        "yac": yac,
                                    },
                                )
                            )
                            return _finalize_play(
                                events,
                                timestamp=time_elapsed,
                                play_type="pass" if released else "run",
                                yards_gained=yards_gained,
                                air_yards=max(0.0, air_yards),
                                yac=yac,
                                duration=time_elapsed,
                                pressure=pressure,
                                sack=False,
                                interception=False,
                                completed=completion_logged,
                                passer_id=passer_id,
                                runner_id=owner_entity.player.player_id,
                                receiver_id=owner_entity.player.player_id if released else None,
                            )
            else:
                # defensive possession (interception return). Treat as dead ball.
                defender = owner_entity
                events.append(
                    PlayEvent(
                        type="tackle",
                        timestamp=time_elapsed,
                        team="offense",
                        player_id=runner_id,
                        target_id=defender.player.player_id,
                        yards=0.0,
                        metadata={
                            "play_type": "turnover",
                            "passer_id": passer_id,
                        },
                    )
                )
                return _finalize_play(
                    events,
                    timestamp=time_elapsed,
                    play_type="pass",
                    yards_gained=0.0,
                    air_yards=max(0.0, air_yards),
                    yac=0.0,
                    duration=time_elapsed,
                    pressure=pressure,
                    sack=False,
                    interception=True,
                    completed=False,
                    passer_id=passer_id,
                    runner_id=None,
                    receiver_id=None,
                )

    # clock expired
    if ball.owner_id:
        owner_entity = offenses.get(ball.owner_id)
        if owner_entity:
            yards_gained = _yard_line(owner_entity.position[1])
            yac = max(0.0, yards_gained - max(0.0, air_yards)) if released else 0.0
            if released:
                yac = max(0.0, min(100.0, yac * TUNING.yac_mod))
                yards_gained = max(0.0, min(100.0, max(0.0, air_yards) + yac))
            else:
                yards_gained = max(0.0, min(100.0, yards_gained * TUNING.rush_block_mod))
            events.append(
                PlayEvent(
                    type="tackle",
                    timestamp=duration,
                    team="defense",
                    player_id=None,
                    target_id=owner_entity.player.player_id,
                    yards=yards_gained,
                    metadata={
                        "play_type": "pass" if released else "run",
                        "passer_id": passer_id,
                        "runner_id": owner_entity.player.player_id,
                        "receiver_id": owner_entity.player.player_id if released else None,
                        "air_yards": max(0.0, air_yards),
                        "yac": yac,
                    },
                )
            )
            return _finalize_play(
                events,
                timestamp=duration,
                play_type="pass" if released else "run",
                yards_gained=yards_gained,
                air_yards=max(0.0, air_yards),
                yac=yac,
                duration=duration,
                pressure=pressure,
                sack=False,
                interception=False,
                completed=completion_logged,
                passer_id=passer_id,
                runner_id=owner_entity.player.player_id,
                receiver_id=owner_entity.player.player_id if released else None,
            )

    return _finalize_play(
        events,
        timestamp=duration,
        play_type="pass" if released else "run",
        yards_gained=0.0,
        air_yards=max(0.0, air_yards),
        yac=0.0,
        duration=duration,
        pressure=pressure,
        sack=sack,
        interception=interception,
        completed=completed,
        passer_id=passer_id,
        runner_id=runner_id,
        receiver_id=receiver_id,
    )


class _SeededRandom:
    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFFFFFFFFFF

    def _rand(self) -> float:
        x = self._state
        x ^= (x >> 12) & 0xFFFFFFFFFFFFFFFF
        x ^= (x << 25) & 0xFFFFFFFFFFFFFFFF
        x ^= (x >> 27) & 0xFFFFFFFFFFFFFFFF
        self._state = x
        return ((x * 2685821657736338717) & 0xFFFFFFFFFFFFFFFF) / 2**64

    def random(self) -> float:
        return self._rand()

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self._rand()

    def normal(self, mean: float, std_dev: float) -> float:
        u1 = max(1e-9, self._rand())
        u2 = self._rand()
        z0 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)
        return mean + std_dev * z0


def _initialise_offense_entities(
    play: Play, roster: Dict[str, Player], modifiers: Dict[str, float]
) -> Dict[str, _Entity]:
    entities: Dict[str, _Entity] = {}
    for index, assignment in enumerate(play.assignments):
        player = roster.get(assignment.player_id)
        if not player:
            raise ValueError(f"Missing offensive player for assignment {assignment.player_id}")
        route = list(assignment.route) if assignment.route else _default_route(assignment, index)
        start_point = route[0]
        entity = _Entity(
            player=player,
            role=assignment.role,
            team="offense",
            route=route,
            position=[start_point.x, start_point.y],
            velocity=[0.0, 0.0],
            base_speed=_base_speed(player.attributes.speed) * modifiers.get(player.player_id, 1.0),
        )
        entities[player.player_id] = entity
    return entities


def _initialise_defense_entities(
    roster: Dict[str, Player], modifiers: Dict[str, float]
) -> Dict[str, _Entity]:
    entities: Dict[str, _Entity] = {}
    for index, player in enumerate(roster.values()):
        if index >= 11:
            break
        x = (index - 5) * 2.0
        y = 10.0 if index < 4 else 8.0
        route = [RoutePoint(timestamp=0.0, x=x, y=y)]
        entities[player.player_id] = _Entity(
            player=player,
            role="defend",
            team="defense",
            route=route,
            position=[x, y],
            velocity=[0.0, 0.0],
            base_speed=_base_speed(player.attributes.speed) * 0.85 * modifiers.get(player.player_id, 1.0),
        )
    return entities


def _default_route(assignment: Assignment, index: int) -> List[RoutePoint]:
    role = assignment.role
    if role == "pass":
        return [
            RoutePoint(timestamp=0.0, x=0.0, y=0.0),
            RoutePoint(timestamp=1.0, x=0.0, y=0.5),
        ]
    if role == "carry":
        lane_x = (index - 2) * 1.5
        return [
            RoutePoint(timestamp=0.0, x=lane_x, y=0.0),
            RoutePoint(timestamp=2.0, x=lane_x, y=7.0),
        ]
    if role == "route":
        start_x = (index - 2) * 3.0
        return [
            RoutePoint(timestamp=0.0, x=start_x, y=0.0),
            RoutePoint(timestamp=2.0, x=start_x, y=12.0),
        ]
    return [RoutePoint(timestamp=0.0, x=(index - 2) * 1.2, y=0.0)]


def _select_qb(offenses: Dict[str, _Entity]) -> Optional[_Entity]:
    for entity in offenses.values():
        if entity.role == "pass":
            return entity
    return None


def _find_primary_receiver(play: Play) -> Optional[Assignment]:
    for assignment in play.assignments:
        if assignment.role == "route":
            return assignment
    return None


def _find_primary_carrier(offenses: Dict[str, _Entity]) -> Optional[_Entity]:
    for entity in offenses.values():
        if entity.role == "carry":
            return entity
    return next(iter(offenses.values()), None)


def _sample_pass_release(qb: Optional[_Entity], rng: _SeededRandom) -> Optional[float]:
    if not qb:
        return None
    awareness = qb.player.attributes.awareness
    base = 1.4 - (awareness - 70) * 0.015
    return max(0.6, min(2.4, base + rng.normal(0.0, 0.12)))


def _advance_entity(
    entity: _Entity,
    time_elapsed: float,
    dt: float,
    fatigue: float,
    *,
    override_target: Optional[List[float]] = None,
) -> None:
    target_pos = override_target or _route_position(entity.route, time_elapsed)
    direction = [target_pos[0] - entity.position[0], target_pos[1] - entity.position[1]]
    distance = _length(direction)
    if distance > 1e-6:
        direction_unit = [direction[0] / distance, direction[1] / distance]
    else:
        direction_unit = [0.0, 0.0]
    desired_speed = entity.base_speed * fatigue
    desired_velocity = [direction_unit[0] * desired_speed, direction_unit[1] * desired_speed]
    delta_v = [desired_velocity[0] - entity.velocity[0], desired_velocity[1] - entity.velocity[1]]
    delta_mag = _length(delta_v)
    max_delta = MAX_ACCEL * dt
    if delta_mag > max_delta and delta_mag > 0:
        scale = max_delta / delta_mag
        delta_v = [delta_v[0] * scale, delta_v[1] * scale]
    entity.velocity[0] += delta_v[0]
    entity.velocity[1] += delta_v[1]
    entity.position[0] += entity.velocity[0] * dt
    entity.position[1] += entity.velocity[1] * dt


def _route_position(route: List[RoutePoint], t: float) -> List[float]:
    if not route:
        return [0.0, 0.0]
    if t <= route[0].timestamp:
        return [route[0].x, route[0].y]
    for start, end in zip(route, route[1:]):
        if start.timestamp <= t <= end.timestamp:
            total = end.timestamp - start.timestamp
            ratio = (t - start.timestamp) / total if total else 0.0
            x = start.x + (end.x - start.x) * ratio
            y = start.y + (end.y - start.y) * ratio
            return [x, y]
    last = route[-1]
    return [last.x, last.y]


def _predict_route_position(entity: _Entity, current_time: float, release_time: float, rng: _SeededRandom) -> List[float]:
    target_time = current_time + max(0.2, release_time * 0.5)
    predicted = _route_position(entity.route, target_time)
    wobble = rng.normal(0.0, 0.5)
    return [predicted[0] + wobble, predicted[1]]


def _accuracy_std(accuracy: int) -> float:
    return max(0.2, (100 - accuracy) / 25.0)


def _defense_target_position(ball: _BallState, defender: _Entity, offenses: Dict[str, _Entity], defenses: Dict[str, _Entity]) -> List[float]:
    if ball.in_air and ball.target_owner_id:
        target = offenses.get(ball.target_owner_id)
        if target:
            return list(target.position)
    if ball.owner_id:
        owner = offenses.get(ball.owner_id) or defenses.get(ball.owner_id)
        if owner:
            return list(owner.position)
    qb = _select_qb(offenses)
    if qb:
        return list(qb.position)
    fallback = _find_primary_carrier(offenses)
    if fallback:
        return list(fallback.position)
    return [0.0, 0.0]


def _nearest_defender(position: List[float], defenders: Iterable[_Entity]) -> Optional[_Entity]:
    best: Optional[_Entity] = None
    best_dist = float("inf")
    for defender in defenders:
        dist = _distance(position, defender.position)
        if dist < best_dist:
            best_dist = dist
            best = defender
    return best


def _resolve_catch(
    qb: Optional[_Entity],
    receiver: Optional[_Entity],
    defender: Optional[_Entity],
    rng: _SeededRandom,
) -> tuple[bool, bool]:
    if not qb or not receiver:
        return False, False
    qb_skill = (qb.player.attributes.accuracy + qb.player.attributes.throwing_power) / 2
    wr_skill = (receiver.player.attributes.catching + receiver.player.attributes.agility) / 2
    defender_skill = 50
    if defender:
        defender_skill = (defender.player.attributes.awareness + defender.player.attributes.agility) / 2
    spread = (qb_skill + wr_skill) - defender_skill
    completion_prob = min(0.99, _logistic(spread / 12.0) * TUNING.completion_mod)
    if rng.random() < completion_prob:
        return True, False
    interception_chance = min(0.95, _logistic((defender_skill - qb_skill) / 15.0) * 0.35 * TUNING.int_mod)
    return False, rng.random() < interception_chance


def _attempt_tackle(tackler: Attributes, runner: Attributes, rng: _SeededRandom) -> bool:
    tackle_skill = (tackler.tackling + tackler.awareness) / 2
    evade_skill = (runner.agility + runner.strength) / 2
    diff = (tackle_skill - evade_skill) / 20.0
    return rng.random() < _logistic(diff)


def _base_speed(rating: int) -> float:
    return 4.0 + (rating / 100.0) * 6.5


def _length(vector: List[float]) -> float:
    return math.sqrt(vector[0] ** 2 + vector[1] ** 2)


def _distance(a: List[float], b: List[float]) -> float:
    return _length([a[0] - b[0], a[1] - b[1]])


def _yard_line(y_position: float) -> float:
    return y_position


def _logistic(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def _finalize_play(
    events: List[PlayEvent],
    *,
    timestamp: float,
    play_type: str,
    yards_gained: float,
    air_yards: float,
    yac: float,
    duration: float,
    pressure: bool,
    sack: bool,
    interception: bool,
    completed: bool,
    passer_id: Optional[str],
    runner_id: Optional[str],
    receiver_id: Optional[str],
) -> PlayResult:
    success = yards_gained >= 4.0
    events.append(
        PlayEvent(
            type="play_end",
            timestamp=timestamp,
            team="offense",
            player_id=runner_id,
            target_id=receiver_id,
            yards=yards_gained,
            metadata={
                "play_type": play_type,
                "passer_id": passer_id,
                "runner_id": runner_id,
                "receiver_id": receiver_id,
                "air_yards": air_yards,
                "yac": yac,
                "success": success,
                "interception": interception,
                "sack": sack,
                "completed": completed,
                "pressure": pressure,
            },
        )
    )
    return PlayResult(
        play_type=play_type,
        yards_gained=yards_gained,
        air_yards=air_yards,
        yac=yac,
        duration=duration,
        pressure=pressure,
        sack=sack,
        interception=interception,
        completed=completed,
        events=list(events),
    )
