from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Dict, Iterable, List, Mapping

from domain.models import Attributes, Player


@dataclass(frozen=True)
class Prospect:
    prospect_id: str
    position: str
    name: str
    hidden_attributes: Attributes
    public_attributes: Attributes

    def as_player(self) -> Player:
        return Player(
            player_id=self.prospect_id,
            name=self.name,
            position=self.position,
            jersey_number=rookie_number(self.position),
            attributes=self.hidden_attributes,
        )


POSITION_ARCHETYPES: Mapping[str, Dict[str, tuple[int, int]]] = {
    "QB": {
        "speed": (65, 85),
        "strength": (60, 80),
        "agility": (70, 90),
        "awareness": (65, 95),
        "catching": (40, 60),
        "tackling": (30, 50),
        "throwing_power": (80, 99),
        "accuracy": (78, 98),
    },
    "RB": {
        "speed": (80, 99),
        "strength": (65, 85),
        "agility": (82, 99),
        "awareness": (60, 82),
        "catching": (60, 85),
        "tackling": (35, 55),
        "throwing_power": (40, 60),
        "accuracy": (40, 60),
    },
    "WR": {
        "speed": (85, 99),
        "strength": (55, 75),
        "agility": (90, 99),
        "awareness": (60, 85),
        "catching": (70, 95),
        "tackling": (35, 55),
        "throwing_power": (30, 50),
        "accuracy": (35, 55),
    },
    "TE": {
        "speed": (74, 88),
        "strength": (70, 90),
        "agility": (65, 82),
        "awareness": (65, 88),
        "catching": (68, 92),
        "tackling": (50, 68),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    "OL": {
        "speed": (50, 68),
        "strength": (85, 99),
        "agility": (58, 75),
        "awareness": (70, 92),
        "catching": (30, 45),
        "tackling": (60, 80),
        "throwing_power": (30, 45),
        "accuracy": (30, 45),
    },
    "DL": {
        "speed": (68, 88),
        "strength": (85, 99),
        "agility": (70, 88),
        "awareness": (65, 85),
        "catching": (45, 65),
        "tackling": (80, 99),
        "throwing_power": (35, 50),
        "accuracy": (30, 45),
    },
    "LB": {
        "speed": (76, 92),
        "strength": (75, 92),
        "agility": (78, 90),
        "awareness": (70, 90),
        "catching": (55, 75),
        "tackling": (82, 99),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    "CB": {
        "speed": (88, 99),
        "strength": (55, 75),
        "agility": (90, 99),
        "awareness": (65, 90),
        "catching": (65, 88),
        "tackling": (55, 75),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    "S": {
        "speed": (82, 94),
        "strength": (65, 85),
        "agility": (80, 92),
        "awareness": (72, 90),
        "catching": (58, 82),
        "tackling": (78, 96),
        "throwing_power": (35, 55),
        "accuracy": (35, 55),
    },
    "K": {
        "speed": (48, 65),
        "strength": (60, 80),
        "agility": (55, 75),
        "awareness": (60, 82),
        "catching": (35, 55),
        "tackling": (35, 55),
        "throwing_power": (75, 90),
        "accuracy": (80, 96),
    },
    "P": {
        "speed": (48, 65),
        "strength": (60, 80),
        "agility": (55, 75),
        "awareness": (60, 82),
        "catching": (35, 55),
        "tackling": (35, 55),
        "throwing_power": (70, 85),
        "accuracy": (72, 88),
    },
}


def generate_draft_class(
    year: int,
    size_by_position: Mapping[str, int],
    *,
    seed: int = 0,
    noise_std: int = 6,
) -> List[Prospect]:
    rng = Random(seed)
    prospects: List[Prospect] = []
    for position, count in size_by_position.items():
        archetype = POSITION_ARCHETYPES[position]
        for index in range(count):
            prospect_id = f"{year}_{position}_{index:03d}"
            name = f"{position.title()} Prospect {index + 1}"
            hidden = _random_attributes(rng, archetype)
            public = _noisy_copy(hidden, rng, noise_std)
            prospects.append(
                Prospect(
                    prospect_id=prospect_id,
                    position=position,
                    name=name,
                    hidden_attributes=hidden,
                    public_attributes=public,
                )
            )
    return prospects


def run_draft(
    teams: Dict[str, List[Player]],
    prospects: Iterable[Prospect],
    *,
    seed: int = 0,
) -> Dict[str, List[Player]]:
    rng = Random(seed)
    order = list(teams.keys())
    picks_per_round = len(order)
    rounds = len(list(prospects)) // picks_per_round
    remaining = list(prospects)
    selected: Dict[str, List[Player]] = {team: list(roster) for team, roster in teams.items()}
    for round_index in range(rounds):
        if round_index % 2 == 1:
            round_order = list(reversed(order))
        else:
            round_order = list(order)
        for team_id in round_order:
            if not remaining:
                break
            choice_index = rng.randrange(len(remaining))
            prospect = remaining.pop(choice_index)
            selected[team_id].append(prospect.as_player())
    return selected


def rookie_number(position: str) -> int:
    return {
        "QB": 12,
        "RB": 26,
        "WR": 18,
    }.get(position, 40)


def _random_attributes(rng: Random, archetype: Mapping[str, tuple[int, int]]) -> Attributes:
    values = {
        key: rng.randint(low, high)
        for key, (low, high) in archetype.items()
    }
    return Attributes(**values)


def _noisy_copy(attributes: Attributes, rng: Random, std: int) -> Attributes:
    values = {}
    for field_name, value in attributes.__dict__.items():
        noise = rng.randint(-std, std)
        values[field_name] = int(max(0, min(99, value + noise / 1.5)))
    return Attributes(**values)
