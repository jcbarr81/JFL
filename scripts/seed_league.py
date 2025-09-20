from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Iterable

from sqlalchemy import func
from sqlmodel import select

import domain.db as db
from domain.db import PositionEnum, PlayerRow, TeamRow, create_all, get_session
from domain.models import Play

DEFAULT_SEED = 20250919

TEAM_DEFINITIONS: list[dict[str, str]] = [
    {"team_id": "ATX", "name": "Austin Armadillos", "city": "Austin", "abbreviation": "ATX"},
    {"team_id": "BOS", "name": "Boston Brigade", "city": "Boston", "abbreviation": "BOS"},
    {"team_id": "CHI", "name": "Chicago Cyclones", "city": "Chicago", "abbreviation": "CHI"},
    {"team_id": "DEN", "name": "Denver Mountaineers", "city": "Denver", "abbreviation": "DEN"},
]

ROSTER_TEMPLATE: dict[PositionEnum, int] = {
    PositionEnum.QB: 2,
    PositionEnum.RB: 3,
    PositionEnum.WR: 6,
    PositionEnum.TE: 2,
    PositionEnum.OL: 7,
    PositionEnum.DL: 6,
    PositionEnum.LB: 5,
    PositionEnum.CB: 4,
    PositionEnum.S: 3,
    PositionEnum.K: 1,
    PositionEnum.P: 1,
}

PLAYERS_PER_TEAM = sum(ROSTER_TEMPLATE.values())

JERSEY_NUMBER_RANGES: dict[PositionEnum, tuple[int, int]] = {
    PositionEnum.QB: (1, 19),
    PositionEnum.RB: (20, 49),
    PositionEnum.WR: (10, 19),
    PositionEnum.TE: (80, 89),
    PositionEnum.OL: (50, 79),
    PositionEnum.DL: (60, 79),
    PositionEnum.LB: (40, 59),
    PositionEnum.CB: (20, 49),
    PositionEnum.S: (20, 49),
    PositionEnum.K: (1, 19),
    PositionEnum.P: (1, 19),
}

DEFAULT_ATTRIBUTE_RANGE = {
    "speed": (55, 80),
    "strength": (55, 80),
    "agility": (55, 80),
    "awareness": (55, 80),
    "catching": (55, 80),
    "tackling": (55, 80),
    "throwing_power": (40, 70),
    "accuracy": (40, 70),
}

ATTRIBUTE_RANGES: dict[PositionEnum, dict[str, tuple[int, int]]] = {
    PositionEnum.QB: {
        "speed": (60, 80),
        "strength": (55, 75),
        "agility": (70, 88),
        "awareness": (72, 95),
        "catching": (35, 60),
        "tackling": (30, 55),
        "throwing_power": (80, 95),
        "accuracy": (78, 94),
    },
    PositionEnum.RB: {
        "speed": (80, 96),
        "strength": (60, 80),
        "agility": (82, 95),
        "awareness": (60, 80),
        "catching": (60, 85),
        "tackling": (40, 65),
        "throwing_power": (35, 55),
        "accuracy": (30, 50),
    },
    PositionEnum.WR: {
        "speed": (85, 98),
        "strength": (55, 75),
        "agility": (85, 98),
        "awareness": (60, 85),
        "catching": (70, 95),
        "tackling": (35, 55),
        "throwing_power": (30, 50),
        "accuracy": (35, 55),
    },
    PositionEnum.TE: {
        "speed": (70, 85),
        "strength": (70, 90),
        "agility": (65, 80),
        "awareness": (65, 85),
        "catching": (68, 90),
        "tackling": (50, 70),
        "throwing_power": (30, 50),
        "accuracy": (30, 50),
    },
    PositionEnum.OL: {
        "speed": (50, 65),
        "strength": (85, 99),
        "agility": (55, 72),
        "awareness": (70, 92),
        "catching": (30, 45),
        "tackling": (55, 80),
        "throwing_power": (30, 45),
        "accuracy": (30, 45),
    },
    PositionEnum.DL: {
        "speed": (65, 82),
        "strength": (80, 98),
        "agility": (70, 85),
        "awareness": (65, 85),
        "catching": (40, 60),
        "tackling": (78, 96),
        "throwing_power": (30, 45),
        "accuracy": (30, 45),
    },
    PositionEnum.LB: {
        "speed": (75, 90),
        "strength": (75, 90),
        "agility": (75, 90),
        "awareness": (70, 90),
        "catching": (55, 75),
        "tackling": (80, 97),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    PositionEnum.CB: {
        "speed": (85, 99),
        "strength": (55, 72),
        "agility": (88, 99),
        "awareness": (65, 88),
        "catching": (65, 90),
        "tackling": (55, 75),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    PositionEnum.S: {
        "speed": (80, 92),
        "strength": (65, 85),
        "agility": (80, 92),
        "awareness": (70, 90),
        "catching": (60, 85),
        "tackling": (78, 94),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    PositionEnum.K: {
        "speed": (50, 70),
        "strength": (55, 75),
        "agility": (55, 75),
        "awareness": (60, 85),
        "catching": (40, 60),
        "tackling": (40, 65),
        "throwing_power": (70, 85),
        "accuracy": (78, 95),
    },
    PositionEnum.P: {
        "speed": (50, 70),
        "strength": (60, 78),
        "agility": (55, 75),
        "awareness": (60, 85),
        "catching": (45, 65),
        "tackling": (40, 65),
        "throwing_power": (68, 85),
        "accuracy": (70, 90),
    },
}

FIRST_NAMES = [
    "Jordan",
    "Alex",
    "Chris",
    "Taylor",
    "Morgan",
    "Dakota",
    "Riley",
    "Cameron",
    "Hayden",
    "Skyler",
    "Logan",
    "Peyton",
    "Avery",
    "Reese",
    "Rowan",
    "Sawyer",
    "Micah",
    "Quinn",
    "Reid",
    "Parker",
]

LAST_NAMES = [
    "Johnson",
    "Andrews",
    "Bailey",
    "Carter",
    "Daniels",
    "Ellis",
    "Fletcher",
    "Griffin",
    "Harrison",
    "Iverson",
    "Jacobs",
    "Keller",
    "Lawson",
    "Mitchell",
    "Nolan",
    "Owens",
    "Patterson",
    "Ramsey",
    "Sloan",
    "Turner",
]

SAMPLE_PLAYS: list[tuple[str, dict]] = [
    (
        "quick_slant_right.json",
        {
            "play_id": "quick_slant_right",
            "name": "Quick Slant Right",
            "formation": "Shotgun Trips Right",
            "personnel": "11",
            "play_type": "offense",
            "assignments": [
                {"player_id": "QB1", "role": "pass", "route": None},
                {
                    "player_id": "WR1",
                    "role": "route",
                    "route": [
                        {"timestamp": 0.0, "x": -5.0, "y": 0.0},
                        {"timestamp": 1.1, "x": -2.0, "y": 8.0},
                    ],
                },
                {
                    "player_id": "WR2",
                    "role": "route",
                    "route": [
                        {"timestamp": 0.0, "x": 5.0, "y": 0.0},
                        {"timestamp": 1.3, "x": 8.0, "y": 6.0},
                    ],
                },
                {"player_id": "RB1", "role": "carry", "route": None},
                {"player_id": "LT", "role": "block", "route": None},
                {"player_id": "LG", "role": "block", "route": None},
                {"player_id": "C", "role": "block", "route": None},
                {"player_id": "RG", "role": "block", "route": None},
                {"player_id": "RT", "role": "block", "route": None},
            ],
        },
    ),
    (
        "cover_two_zone.json",
        {
            "play_id": "cover_two_zone",
            "name": "Cover Two Zone",
            "formation": "Nickel Over",
            "personnel": "Nickel",
            "play_type": "defense",
            "assignments": [
                {
                    "player_id": "CB1",
                    "role": "defend",
                    "route": [
                        {"timestamp": 0.0, "x": -12.0, "y": 3.0},
                        {"timestamp": 1.5, "x": -15.0, "y": 12.0},
                    ],
                },
                {
                    "player_id": "CB2",
                    "role": "defend",
                    "route": [
                        {"timestamp": 0.0, "x": 12.0, "y": 3.0},
                        {"timestamp": 1.5, "x": 15.0, "y": 12.0},
                    ],
                },
                {
                    "player_id": "S1",
                    "role": "defend",
                    "route": [
                        {"timestamp": 0.0, "x": -8.0, "y": 12.0},
                        {"timestamp": 1.8, "x": -8.0, "y": 25.0},
                    ],
                },
                {
                    "player_id": "S2",
                    "role": "defend",
                    "route": [
                        {"timestamp": 0.0, "x": 8.0, "y": 12.0},
                        {"timestamp": 1.8, "x": 8.0, "y": 25.0},
                    ],
                },
                {"player_id": "LB1", "role": "defend", "route": None},
                {"player_id": "LB2", "role": "defend", "route": None},
                {"player_id": "DE1", "role": "rush", "route": None},
                {"player_id": "DE2", "role": "rush", "route": None},
            ],
        },
    ),
    (
        "punt_right.json",
        {
            "play_id": "punt_right",
            "name": "Punt Right",
            "formation": "Punt Spread",
            "personnel": "Punt",
            "play_type": "special_teams",
            "assignments": [
                {"player_id": "P1", "role": "kick", "route": None},
                {"player_id": "PP", "role": "hold", "route": None},
                {"player_id": "GUN1", "role": "route", "route": [
                    {"timestamp": 0.0, "x": -8.0, "y": 0.0},
                    {"timestamp": 2.0, "x": -6.0, "y": 30.0},
                ]},
                {"player_id": "GUN2", "role": "route", "route": [
                    {"timestamp": 0.0, "x": 8.0, "y": 0.0},
                    {"timestamp": 2.0, "x": 6.0, "y": 30.0},
                ]},
                {"player_id": "LS", "role": "block", "route": None},
                {"player_id": "PP2", "role": "block", "route": None},
                {"player_id": "PP3", "role": "block", "route": None},
            ],
        },
    ),
]


@dataclass
class SeedSummary:
    teams: int
    players: int
    plays_written: int


def _random_name(rng: Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _attribute_for(position: PositionEnum, attribute: str, rng: Random) -> int:
    low, high = ATTRIBUTE_RANGES.get(position, DEFAULT_ATTRIBUTE_RANGE).get(attribute, DEFAULT_ATTRIBUTE_RANGE[attribute])
    return rng.randint(low, high)


def _generate_attributes(position: PositionEnum, rng: Random) -> dict[str, int]:
    ranges = ATTRIBUTE_RANGES.get(position, DEFAULT_ATTRIBUTE_RANGE)
    return {key: rng.randint(low, high) for key, (low, high) in ranges.items()}


def _jersey_number(position: PositionEnum, rng: Random, assigned: set[int]) -> int:
    low, high = JERSEY_NUMBER_RANGES.get(position, (1, 99))
    for _ in range(10):
        candidate = rng.randint(low, high)
        if candidate not in assigned:
            assigned.add(candidate)
            return candidate
    # fallback in unlikely case of range exhaustion
    candidate = low
    while candidate in assigned and candidate <= high:
        candidate += 1
    assigned.add(candidate)
    return candidate


def _players_for_team(team: dict[str, str], rng: Random) -> Iterable[PlayerRow]:
    assigned_numbers: set[int] = set()
    for position, count in ROSTER_TEMPLATE.items():
        for index in range(1, count + 1):
            yield PlayerRow(
                player_id=f"{team['team_id']}-{position.value}{index:02d}",
                name=_random_name(rng),
                position=position,
                jersey_number=_jersey_number(position, rng, assigned_numbers),
                team_id=team["team_id"],
                attributes=_generate_attributes(position, rng),
            )


def _write_sample_plays(target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for filename, payload in SAMPLE_PLAYS:
        Play.model_validate(payload)
        output_path = target_dir / filename
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        written += 1
    return written


def seed_league(*, seed: int = DEFAULT_SEED, plays_dir: Path | None = None) -> SeedSummary:
    """Seed the SQLite database with a tiny league and write sample plays."""

    rng = Random(seed)
    create_all()

    with get_session() as session:
        existing_team_ids = set(session.exec(select(TeamRow.team_id)).all())
        for team in TEAM_DEFINITIONS:
            if team["team_id"] in existing_team_ids:
                logging.getLogger(__name__).info("Team %s already exists, skipping", team["team_id"])
                continue
            session.add(TeamRow(**team))
            for player in _players_for_team(team, rng):
                session.add(player)

    with get_session() as session:
        total_teams = session.exec(select(func.count(TeamRow.team_id))).one()
        total_players = session.exec(select(func.count(PlayerRow.player_id))).one()

    play_dir = plays_dir or Path("data/plays")
    plays_written = _write_sample_plays(play_dir)

    logging.getLogger(__name__).info(
        "Seeded league: %d teams, %d players, wrote %d plays to %s",
        total_teams,
        total_players,
        plays_written,
        play_dir,
    )
    return SeedSummary(teams=total_teams, players=total_players, plays_written=plays_written)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Gridiron Sim tiny league database.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed for deterministic output")
    parser.add_argument(
        "--plays-dir",
        type=Path,
        default=Path("data/plays"),
        help="Directory to write sample play JSON files",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log verbosity",
    )
    args = parser.parse_args()
    logging.basicConfig(level=args.log_level, format="[%(levelname)s] %(message)s")
    seed_league(seed=args.seed, plays_dir=args.plays_dir)


if __name__ == "__main__":
    main()


