from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Literal, Optional

PlayCategory = Literal["run", "pass", "sideline_pass"]


@dataclass(frozen=True)
class OffenseContext:
    down: int
    yards_to_first: float
    yardline: float
    remaining_time: float
    score_diff: int  # offense score minus defense score
    quarter: Optional[int] = None


@dataclass(frozen=True)
class PlayChoice:
    category: PlayCategory


def call_offense(context: OffenseContext, rng: Optional[Random] = None) -> PlayChoice:
    random = rng or Random()

    weights: dict[PlayCategory, float] = {
        "run": 1.0,
        "pass": 1.0,
        "sideline_pass": 0.0,
    }

    yards = context.yards_to_first
    down = context.down
    time = context.remaining_time
    score_diff = context.score_diff

    if down <= 0:
        down = 1
    if yards <= 0:
        yards = 0.5

    if down == 3 and yards >= 7:
        weights["pass"] += 5.0
        weights["run"] *= 0.2
        weights["sideline_pass"] += 1.5
    elif down == 3 and yards <= 2:
        weights["run"] += 4.0
        weights["pass"] *= 0.5
    elif down == 4:
        weights["pass"] += 3.0
        weights["run"] *= 0.3

    if time <= 180.0:
        weights["pass"] += 3.0
        weights["sideline_pass"] += 2.0
        if score_diff < 0:
            weights["pass"] += 2.0
            weights["sideline_pass"] += 3.0
            weights["run"] *= 0.4

    if time <= 120.0:
        weights["sideline_pass"] += 2.0
        weights["pass"] += 2.0
        weights["run"] *= 0.5

    if score_diff > 7 and time <= 240.0:
        weights["run"] += 2.0
        weights["pass"] *= 0.7
        weights["sideline_pass"] *= 0.5

    if context.yardline >= 80.0:
        weights["pass"] += 1.5
        weights["sideline_pass"] += 0.5

    weights = {key: max(0.0, value) for key, value in weights.items()}
    total = sum(weights.values())
    if total == 0:
        return PlayChoice("run")

    roll = random.random() * total
    cumulative = 0.0
    for category, weight in weights.items():
        cumulative += weight
        if roll <= cumulative:
            return PlayChoice(category)
    return PlayChoice("run")


@dataclass(frozen=True)
class DefenseContext:
    down: int
    yards_to_first: float
    yardline: float
    remaining_time: float


@dataclass(frozen=True)
class DefenseChoice:
    front: Literal["even", "odd", "dime", "nickel"]
    coverage: Literal["zone", "man", "press"]
    blitz_rate: float


def call_defense(context: DefenseContext, rng: Optional[Random] = None) -> DefenseChoice:
    random = rng or Random()
    if context.down >= 3 and context.yards_to_first >= 7:
        return DefenseChoice(front="dime", coverage="zone", blitz_rate=0.2)
    if context.down == 3 and context.yards_to_first <= 2:
        return DefenseChoice(front="odd", coverage="press", blitz_rate=0.45)
    if context.yardline <= 20:
        return DefenseChoice(front="even", coverage="press", blitz_rate=0.35)
    choice = random.random()
    if choice < 0.4:
        return DefenseChoice(front="nickel", coverage="zone", blitz_rate=0.25)
    if choice < 0.7:
        return DefenseChoice(front="even", coverage="man", blitz_rate=0.2)
    return DefenseChoice(front="odd", coverage="press", blitz_rate=0.3)
