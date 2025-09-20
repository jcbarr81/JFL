from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from sim.draft import Prospect, generate_draft_class, run_draft


@dataclass
class DraftClassExport:
    prospects: List[Prospect]
    round_count: int


def export_draft_class(prospects: Iterable[Prospect], path: Path) -> None:
    lines = [
        "prospect_id,position,name,speed,strength,agility,awareness,catching,tackling,throwing_power,accuracy"
    ]
    for prospect in prospects:
        attrs = prospect.public_attributes
        lines.append(
            ",".join(
                [
                    prospect.prospect_id,
                    prospect.position,
                    prospect.name,
                    str(attrs.speed),
                    str(attrs.strength),
                    str(attrs.agility),
                    str(attrs.awareness),
                    str(attrs.catching),
                    str(attrs.tackling),
                    str(attrs.throwing_power),
                    str(attrs.accuracy),
                ]
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def simple_draft_setup(team_ids: List[str]) -> Dict[str, list]:
    return {team_id: [] for team_id in team_ids}


__all__ = [
    "DraftClassExport",
    "export_draft_class",
    "generate_draft_class",
    "run_draft",
    "simple_draft_setup",
]
