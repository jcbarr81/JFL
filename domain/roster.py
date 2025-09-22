from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from domain.db import DepthChartRow, DepthUnitEnum, PlayerRow, PositionEnum, engine

LOGGER = logging.getLogger("domain.roster")

# Minimum counts per position group (simplified league rules)
MIN_POSITION_REQUIREMENTS: Dict[PositionEnum, int] = {
    PositionEnum.QB: 2,
    PositionEnum.RB: 3,
    PositionEnum.WR: 5,
    PositionEnum.TE: 2,
    PositionEnum.OL: 8,
    PositionEnum.DL: 7,
    PositionEnum.LB: 6,
    PositionEnum.CB: 5,
    PositionEnum.S: 4,
    PositionEnum.K: 1,
    PositionEnum.P: 1,
}

TARGET_ROSTER_SIZE = 53


@dataclass(frozen=True)
class RosterPlayer:
    player_id: str
    name: str
    position: PositionEnum
    jersey_number: int
    overall: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "position": self.position.value,
            "jersey_number": self.jersey_number,
            "overall": self.overall,
        }

    @staticmethod
    def from_dict(payload: Dict[str, object]) -> "RosterPlayer":
        return RosterPlayer(
            player_id=str(payload["player_id"]),
            name=str(payload["name"]),
            position=PositionEnum(str(payload["position"]).upper()),
            jersey_number=int(payload.get("jersey_number", 0)),
            overall=int(payload.get("overall", 60)),
        )


@dataclass(frozen=True)
class DepthSlot:
    slot_id: int
    unit: DepthUnitEnum
    role: str
    position: PositionEnum
    slot_index: int
    player_id: str | None


DEPTH_CHART_TEMPLATE: Dict[DepthUnitEnum, List[Tuple[str, PositionEnum, int]]] = {
    DepthUnitEnum.OFFENSE: [
        ("QB1", PositionEnum.QB, 0),
        ("QB2", PositionEnum.QB, 1),
        ("RB1", PositionEnum.RB, 0),
        ("RB2", PositionEnum.RB, 1),
        ("WR1", PositionEnum.WR, 0),
        ("WR2", PositionEnum.WR, 1),
        ("WR3", PositionEnum.WR, 2),
        ("TE1", PositionEnum.TE, 0),
        ("TE2", PositionEnum.TE, 1),
        ("OL1", PositionEnum.OL, 0),
        ("OL2", PositionEnum.OL, 1),
        ("OL3", PositionEnum.OL, 2),
        ("OL4", PositionEnum.OL, 3),
        ("OL5", PositionEnum.OL, 4),
    ],
    DepthUnitEnum.DEFENSE: [
        ("DL1", PositionEnum.DL, 0),
        ("DL2", PositionEnum.DL, 1),
        ("DL3", PositionEnum.DL, 2),
        ("LB1", PositionEnum.LB, 0),
        ("LB2", PositionEnum.LB, 1),
        ("LB3", PositionEnum.LB, 2),
        ("CB1", PositionEnum.CB, 0),
        ("CB2", PositionEnum.CB, 1),
        ("S1", PositionEnum.S, 0),
        ("S2", PositionEnum.S, 1),
    ],
    DepthUnitEnum.SPECIAL: [
        ("K", PositionEnum.K, 0),
        ("P", PositionEnum.P, 0),
        ("KR", PositionEnum.WR, 3),
        ("PR", PositionEnum.WR, 4),
    ],
}


class RosterRepository:
    """Access layer for roster and depth chart data."""

    def __init__(self, user_home: Path | None = None) -> None:
        self._engine = engine
        base = user_home or Path.home()
        self._fallback_path = base / "settings" / "rosters.json"
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)

    def _session(self) -> Session:
        return Session(self._engine, expire_on_commit=False)

    # ------------------------------------------------------------------
    # Roster loading / persistence
    # ------------------------------------------------------------------
    def list_players(self, team_id: str) -> List[RosterPlayer]:
        fallback = self._load_fallback_roster(team_id)
        if fallback:
            return [RosterPlayer.from_dict(player) for player in fallback]

        try:
            with self._session() as session:
                rows = session.exec(select(PlayerRow).where(PlayerRow.team_id == team_id)).all()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load roster for %s: %s", team_id, exc)
            rows = []

        players: List[RosterPlayer] = []
        for row in rows:
            attrs = row.attributes or {}
            overall = int(sum(attrs.values()) / len(attrs)) if attrs else 60
            players.append(
                RosterPlayer(
                    player_id=row.player_id,
                    name=row.name,
                    position=row.position,
                    jersey_number=row.jersey_number,
                    overall=overall,
                )
            )

        if not players:
            players = self._generate_fallback_players(team_id)

        self.save_roster(team_id, players)
        return list(players)

    def save_roster(self, team_id: str, players: Iterable[RosterPlayer]) -> None:
        data = self._load_fallback_data()
        data[team_id] = [player.to_dict() for player in players]
        try:
            self._fallback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:  # pragma: no cover
            LOGGER.warning("Unable to write roster fallback file")

    def _load_fallback_data(self) -> Dict[str, List[Dict[str, object]]]:
        if not self._fallback_path.exists():
            return {}
        try:
            return json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("Malformed roster fallback; resetting")
            return {}

    def _load_fallback_roster(self, team_id: str) -> List[Dict[str, object]]:
        return self._load_fallback_data().get(team_id, [])

    def _generate_fallback_players(self, team_id: str) -> List[RosterPlayer]:
        players: List[RosterPlayer] = []
        jersey_seed = abs(hash(team_id)) % 50
        positions = list(MIN_POSITION_REQUIREMENTS.keys())
        total_needed = max(TARGET_ROSTER_SIZE, sum(MIN_POSITION_REQUIREMENTS.values()))
        for idx in range(total_needed):
            position = positions[idx % len(positions)]
            player_id = f"{team_id}_{position.value}_{idx}"
            name = f"{position.value} Reserve {idx + 1}"
            jersey_number = ((jersey_seed + idx * 3) % 90) + 1
            overall = 65 + (idx % 10) * 2
            players.append(
                RosterPlayer(
                    player_id=player_id,
                    name=name,
                    position=position,
                    jersey_number=jersey_number,
                    overall=min(overall, 90),
                )
            )
        return players[:TARGET_ROSTER_SIZE]

    # ------------------------------------------------------------------
    # Depth chart helpers
    # ------------------------------------------------------------------
    def load_depth_chart(self, team_id: str) -> List[DepthSlot]:
        template = DEPTH_CHART_TEMPLATE
        existing: Dict[Tuple[DepthUnitEnum, str], DepthChartRow] = {}
        try:
            with self._session() as session:
                rows = session.exec(select(DepthChartRow).where(DepthChartRow.team_id == team_id)).all()
                for row in rows:
                    existing[(row.unit, row.role)] = row
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load depth chart for %s: %s", team_id, exc)
        slots: List[DepthSlot] = []
        slot_id = 0
        for unit, entries in template.items():
            for role, position, index in entries:
                match = existing.get((unit, role))
                slots.append(
                    DepthSlot(
                        slot_id=slot_id,
                        unit=unit,
                        role=role,
                        position=position,
                        slot_index=index,
                        player_id=match.player_id if match else None,
                    )
                )
                slot_id += 1
        return slots

    def save_depth_chart(self, team_id: str, assignments: Iterable[DepthSlot]) -> None:
        try:
            with self._session() as session:
                for slot in assignments:
                    row = session.exec(
                        select(DepthChartRow).where(
                            DepthChartRow.team_id == team_id,
                            DepthChartRow.unit == slot.unit,
                            DepthChartRow.role == slot.role,
                        )
                    ).one_or_none()
                    if row is None:
                        row = DepthChartRow(
                            team_id=team_id,
                            unit=slot.unit,
                            role=slot.role,
                            position=slot.position,
                            slot_index=slot.slot_index,
                            player_id=slot.player_id,
                        )
                        session.add(row)
                    else:
                        row.player_id = slot.player_id
                    session.add(row)
                session.commit()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to save depth chart for %s: %s", team_id, exc)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------
    def auto_fix(self, team_id: str) -> List[DepthSlot]:
        players = self.list_players(team_id)
        by_position: Dict[PositionEnum, List[RosterPlayer]] = {}
        for player in players:
            by_position.setdefault(player.position, []).append(player)
        for group in by_position.values():
            group.sort(key=lambda p: p.overall, reverse=True)
        slots = self.load_depth_chart(team_id)
        for slot in slots:
            candidates = by_position.get(slot.position, [])
            idx = min(slot.slot_index, len(candidates) - 1)
            slot.player_id = candidates[idx].player_id if candidates else None
        self.save_depth_chart(team_id, slots)
        return slots

    def validate(self, team_id: str, slots: Iterable[DepthSlot]) -> List[str]:
        players = self.list_players(team_id)
        warnings: List[str] = []
        if len(players) != TARGET_ROSTER_SIZE:
            warnings.append(f"Roster size is {len(players)}; target is {TARGET_ROSTER_SIZE} players.")
        counts: Dict[PositionEnum, int] = {pos: 0 for pos in PositionEnum}
        for player in players:
            counts[player.position] += 1
        for position, minimum in MIN_POSITION_REQUIREMENTS.items():
            if counts.get(position, 0) < minimum:
                warnings.append(
                    f"Minimum requirement for {position.value} is {minimum}. Currently {counts.get(position, 0)}."
                )
        assigned = [slot.player_id for slot in slots if slot.player_id]
        if len(set(assigned)) != len(assigned):
            warnings.append("Some players are assigned to multiple depth slots.")
        return warnings


def slots_by_unit(slots: Iterable[DepthSlot]) -> Dict[DepthUnitEnum, List[DepthSlot]]:
    grouped: Dict[DepthUnitEnum, List[DepthSlot]] = {unit: [] for unit in DepthUnitEnum}
    for slot in slots:
        grouped.setdefault(slot.unit, []).append(slot)
    for unit_slots in grouped.values():
        unit_slots.sort(key=lambda slot: (slot.position.value, slot.slot_index))
    return grouped
