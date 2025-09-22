from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from domain.db import ContractRow, engine
from domain.roster import MIN_POSITION_REQUIREMENTS, RosterPlayer, RosterRepository

LOGGER = logging.getLogger("domain.contracts")

CAP_LIMIT = 210_000_000.0


@dataclass
class ContractRecord:
    contract_id: str
    player_id: str
    team_id: str
    player_name: str
    position: str
    years: int
    base_salary: float
    signing_bonus: float
    signing_year: int
    status: str = "Active"

    @property
    def cap_hit(self) -> float:
        years = max(1, self.years)
        return float(self.base_salary + (self.signing_bonus / years))

    def to_dict(self) -> Dict[str, object]:
        return {
            "contract_id": self.contract_id,
            "player_id": self.player_id,
            "team_id": self.team_id,
            "player_name": self.player_name,
            "position": self.position,
            "years": self.years,
            "base_salary": self.base_salary,
            "signing_bonus": self.signing_bonus,
            "signing_year": self.signing_year,
            "status": self.status,
        }


@dataclass
class CapSummary:
    cap_limit: float
    cap_used: float
    cap_available: float
    dead_money: float


class ContractsRepository:
    """Persistence helper for contracts and salary cap calculations."""

    def __init__(self, user_home: Path) -> None:
        self._engine = engine
        self._fallback_path = user_home / "settings" / "contracts.json"
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._exports_dir = user_home / "exports"
        self._roster_repo = RosterRepository(user_home)
        self._cache: Dict[str, List[ContractRecord]] = {}

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------
    def list_contracts(self, team_id: str) -> List[ContractRecord]:
        if team_id in self._cache:
            return [replace(c) for c in self._cache[team_id]]
        contracts = self._load_from_db(team_id)
        if not contracts:
            contracts = self._load_from_json(team_id)
        if not contracts:
            contracts = self._generate_contracts(team_id)
            self._persist_bulk(team_id, contracts)
        self._cache[team_id] = [replace(c) for c in contracts]
        return [replace(c) for c in contracts]

    def _session(self) -> Session:
        return Session(self._engine, expire_on_commit=False)

    def _load_from_db(self, team_id: str) -> List[ContractRecord]:
        try:
            with self._session() as session:
                rows = session.exec(select(ContractRow).where(ContractRow.team_id == team_id)).all()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to load contracts for %s: %s", team_id, exc)
            return []
        return [self._row_to_contract(row) for row in rows]

    def _load_from_json(self, team_id: str) -> List[ContractRecord]:
        if not self._fallback_path.exists():
            return []
        try:
            data = json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:  # pragma: no cover - defensive
            LOGGER.warning("Malformed contracts fallback; resetting")
            return []
        contracts: List[ContractRecord] = []
        for payload in data.get(team_id, []):
            try:
                contracts.append(ContractRecord(**payload))
            except TypeError:
                continue
        return contracts

    def _generate_contracts(self, team_id: str) -> List[ContractRecord]:
        players = self._roster_repo.list_players(team_id)
        if not players:
            players = self._generate_placeholder_roster(team_id)
        current_year = datetime.utcnow().year
        contracts: List[ContractRecord] = []
        for player in players:
            base_salary = 1_200_000 + max(0, player.overall - 60) * 80_000
            signing_bonus = max(0, player.overall - 70) * 60_000
            years = 3 if player.position.value in {"QB", "WR", "OL", "DL"} else 2
            contracts.append(
                ContractRecord(
                    contract_id=f"{player.player_id}-contract",
                    player_id=player.player_id,
                    team_id=team_id,
                    player_name=player.name,
                    position=player.position.value,
                    years=years,
                    base_salary=float(base_salary),
                    signing_bonus=float(signing_bonus),
                    signing_year=current_year,
                )
            )
        return contracts

    def _generate_placeholder_roster(self, team_id: str) -> List[RosterPlayer]:
        placeholder: List[RosterPlayer] = []
        positions = list(MIN_POSITION_REQUIREMENTS.keys())
        for idx in range(53):
            position = positions[idx % len(positions)]
            placeholder.append(
                RosterPlayer(
                    player_id=f"{team_id}_placeholder_{idx}",
                    name=f"Reserve {position.value} {idx + 1}",
                    position=position,
                    jersey_number=10 + idx,
                    overall=65 + (idx % 10),
                )
            )
        return placeholder

    def _row_to_contract(self, row: ContractRow) -> ContractRecord:
        return ContractRecord(
            contract_id=row.contract_id,
            player_id=row.player_id,
            team_id=row.team_id,
            player_name=row.player_name,
            position=row.position.value,
            years=row.years,
            base_salary=row.base_salary,
            signing_bonus=row.signing_bonus,
            signing_year=row.signing_year,
            status=row.status,
        )

    def _persist_bulk(self, team_id: str, contracts: Iterable[ContractRecord]) -> None:
        contracts = list(contracts)
        try:
            with self._session() as session:
                for contract in contracts:
                    row = session.get(ContractRow, contract.contract_id)
                    if row is None:
                        row = ContractRow(contract_id=contract.contract_id)
                    row.player_id = contract.player_id
                    row.team_id = contract.team_id
                    row.player_name = contract.player_name
                    row.position = contract.position  # type: ignore[assignment]
                    row.years = contract.years
                    row.base_salary = contract.base_salary
                    row.signing_bonus = contract.signing_bonus
                    row.signing_year = contract.signing_year
                    row.status = contract.status
                    session.add(row)
                session.commit()
        except SQLAlchemyError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to persist contracts for %s: %s", team_id, exc)
        self._write_fallback(team_id, contracts)

    def _write_fallback(self, team_id: str, contracts: List[ContractRecord]) -> None:
        try:
            data = {}
            if self._fallback_path.exists():
                data = json.loads(self._fallback_path.read_text(encoding="utf-8"))
            data[team_id] = [contract.to_dict() for contract in contracts]
            self._fallback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:  # pragma: no cover - defensive
            LOGGER.warning("Unable to write contracts fallback file")

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------
    def calculate_cap_summary(self, team_id: str) -> CapSummary:
        contracts = self.list_contracts(team_id)
        return self._calculate_summary(contracts)

    def _calculate_summary(self, contracts: Iterable[ContractRecord]) -> CapSummary:
        active = [c for c in contracts if c.status.lower() == "active"]
        inactive = [c for c in contracts if c.status.lower() != "active"]
        cap_used = sum(c.cap_hit for c in active)
        dead_money = sum(max(0.0, c.signing_bonus - (c.signing_bonus / max(1, c.years))) for c in inactive)
        cap_available = CAP_LIMIT - cap_used - dead_money
        return CapSummary(
            cap_limit=CAP_LIMIT,
            cap_used=cap_used,
            cap_available=cap_available,
            dead_money=dead_money,
        )

    def update_contract(self, contract: ContractRecord) -> CapSummary:
        contracts = self.list_contracts(contract.team_id)
        mapping = {c.contract_id: c for c in contracts}
        mapping[contract.contract_id] = contract
        updated = list(mapping.values())
        summary = self._calculate_summary(updated)
        if summary.cap_available < 0:
            raise ValueError(f"Cap exceeded by ${abs(summary.cap_available):,.0f}")
        self._cache[contract.team_id] = [replace(c) for c in updated]
        self._persist_bulk(contract.team_id, updated)
        return summary

    def auto_restructure(self, team_id: str) -> CapSummary:
        contracts = self.list_contracts(team_id)
        contracts.sort(key=lambda c: c.cap_hit, reverse=True)
        summary = self._calculate_summary(contracts)
        if summary.cap_available >= 0:
            return summary
        for idx, contract in enumerate(contracts):
            if summary.cap_available >= 0:
                break
            converted = contract.base_salary * 0.2
            contract = replace(
                contract,
                base_salary=contract.base_salary - converted,
                signing_bonus=contract.signing_bonus + converted,
                years=min(7, contract.years + 1),
            )
            contracts[idx] = contract
            summary = self._calculate_summary(contracts)
        self._cache[team_id] = [replace(c) for c in contracts]
        self._persist_bulk(team_id, contracts)
        return summary

    def export_cap_table(self, team_id: str) -> Path:
        contracts = self.list_contracts(team_id)
        summary = self._calculate_summary(contracts)
        self._exports_dir.mkdir(parents=True, exist_ok=True)
        export_path = self._exports_dir / f"{team_id}_cap_{datetime.utcnow():%Y%m%d%H%M%S}.csv"
        with export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Player", "Position", "Years", "Base Salary", "Signing Bonus", "Cap Hit", "Status"])
            for contract in contracts:
                writer.writerow([
                    contract.player_name,
                    contract.position,
                    contract.years,
                    f"{contract.base_salary:,.0f}",
                    f"{contract.signing_bonus:,.0f}",
                    f"{contract.cap_hit:,.0f}",
                    contract.status,
                ])
            writer.writerow([])
            writer.writerow(["Cap Limit", "", "", f"{summary.cap_limit:,.0f}", "", "", ""])
            writer.writerow(["Cap Used", "", "", f"{summary.cap_used:,.0f}", "", "", ""])
            writer.writerow(["Dead Money", "", "", f"{summary.dead_money:,.0f}", "", "", ""])
            writer.writerow(["Cap Available", "", "", f"{summary.cap_available:,.0f}", "", "", ""])
        return export_path

    def transfer_contract(self, player_id: str, from_team: str, to_team: str) -> tuple[CapSummary, CapSummary]:
        from_contracts = self.list_contracts(from_team)
        to_contracts = self.list_contracts(to_team)
        contract = next((c for c in from_contracts if c.player_id == player_id), None)
        if contract is None:
            return self._calculate_summary(from_contracts), self._calculate_summary(to_contracts)
        from_contracts = [c for c in from_contracts if c.contract_id != contract.contract_id]
        self._cache[from_team] = [replace(c) for c in from_contracts]
        self._persist_bulk(from_team, from_contracts)
        transferred = replace(contract, team_id=to_team)
        to_contracts.append(transferred)
        self._cache[to_team] = [replace(c) for c in to_contracts]
        self._persist_bulk(to_team, to_contracts)
        return self._calculate_summary(from_contracts), self._calculate_summary(to_contracts)
