from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from domain.contracts import CapSummary, ContractsRepository
from domain.roster import MIN_POSITION_REQUIREMENTS, RosterPlayer, RosterRepository
from domain.teams import TeamInfo, TeamRepository

LOGGER = logging.getLogger("domain.trades")


@dataclass(frozen=True)
class TradeAsset:
    asset_id: str
    asset_type: str  # "player" or "pick"
    name: str
    value: float
    metadata: Dict[str, str]


@dataclass(frozen=True)
class TradeEvaluation:
    our_value: float
    their_value: float
    diff: float
    accepted: bool
    message: str
    balance_score: float


@dataclass(frozen=True)
class TradeMovement:
    player_id: str
    from_team: str
    to_team: str


@dataclass
class TradeState:
    snapshot: Dict[str, List[RosterPlayer]] = field(default_factory=dict)
    movements: List[TradeMovement] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "snapshot": {
                team_id: [player.to_dict() for player in players]
                for team_id, players in self.snapshot.items()
            },
            "movements": [
                {
                    "player_id": move.player_id,
                    "from_team": move.from_team,
                    "to_team": move.to_team,
                }
                for move in self.movements
            ],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, object]) -> "TradeState":
        if "snapshot" in payload:
            snapshot_payload = payload.get("snapshot", {})
            movements_payload = payload.get("movements", [])
        else:  # backward compatibility with older format
            snapshot_payload = payload
            movements_payload = []

        snapshot: Dict[str, List[RosterPlayer]] = {}
        if isinstance(snapshot_payload, dict):
            for team_id, players in snapshot_payload.items():
                if not isinstance(players, list):
                    continue
                roster: List[RosterPlayer] = []
                for raw_player in players:
                    if isinstance(raw_player, dict):
                        try:
                            roster.append(RosterPlayer.from_dict(raw_player))
                        except (KeyError, ValueError):  # pragma: no cover - defensive
                            LOGGER.warning("Malformed player snapshot for team %s", team_id)
                snapshot[str(team_id)] = roster

        movements: List[TradeMovement] = []
        if isinstance(movements_payload, list):
            for item in movements_payload:
                if not isinstance(item, dict):
                    continue
                player_id = item.get("player_id")
                from_team = item.get("from_team") or item.get("from")
                to_team = item.get("to_team") or item.get("to")
                if player_id and from_team and to_team:
                    movements.append(
                        TradeMovement(
                            player_id=str(player_id),
                            from_team=str(from_team),
                            to_team=str(to_team),
                        )
                    )
        return cls(snapshot=snapshot, movements=movements)


@dataclass(frozen=True)
class TradeResult:
    our_team_id: str
    their_team_id: str
    our_summary: CapSummary
    their_summary: CapSummary
    evaluation: TradeEvaluation

    def to_payload(self) -> Dict[str, object]:
        return {
            "our_team_id": self.our_team_id,
            "their_team_id": self.their_team_id,
            "our_summary": self.our_summary.__dict__,
            "their_summary": self.their_summary.__dict__,
            "evaluation": {
                "our_value": self.evaluation.our_value,
                "their_value": self.evaluation.their_value,
                "diff": self.evaluation.diff,
                "accepted": self.evaluation.accepted,
                "message": self.evaluation.message,
                "balance_score": self.evaluation.balance_score,
            },
        }


@dataclass(frozen=True)
class TradeUndoResult:
    rosters: Dict[str, List[RosterPlayer]]
    summaries: Dict[str, CapSummary]


class TradeRepository:
    """Manages roster trades, value calculations, and undo support."""

    def __init__(self, user_home: Path) -> None:
        self._user_home = user_home
        self._roster_repo = RosterRepository(user_home)
        self._contracts_repo = ContractsRepository(user_home)
        self._team_repo = TeamRepository()
        self._state_path = user_home / "settings" / "trade_state.json"
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_trade: Optional[TradeState] = None
        self.load_last_trade()

    # ------------------------------------------------------------------
    # Asset helpers
    # ------------------------------------------------------------------
    def list_assets(self, team_id: str) -> Dict[str, List[TradeAsset]]:
        players = self._roster_repo.list_players(team_id)
        return {
            "players": [self._player_to_asset(player) for player in players],
            "picks": self._generate_picks(team_id),
        }

    def _player_to_asset(self, player: RosterPlayer) -> TradeAsset:
        age = 22 + abs(hash(player.player_id)) % 15
        contract = self._find_contract(player.player_id, player.position.value)
        cap_hit = contract.cap_hit if contract else float(player.overall * 150_000)
        base_value = float(player.overall * 1.8 - age * 0.6 - (cap_hit / 1_000_000) * 0.8)
        scarcity = MIN_POSITION_REQUIREMENTS.get(player.position, 4)
        scarcity_factor = 1.0 + (1.5 / max(1, scarcity))
        value = max(base_value * scarcity_factor, 1.0)
        metadata = {
            "player_id": player.player_id,
            "position": player.position.value,
            "overall": str(player.overall),
            "age": str(age),
            "cap_hit": f"{cap_hit:,.0f}",
        }
        if contract is not None:
            metadata.update(
                {
                    "contract_years": str(contract.years),
                    "contract_status": contract.status,
                }
            )
        return TradeAsset(
            asset_id=f"player:{player.player_id}",
            asset_type="player",
            name=f"{player.name} ({player.position.value})",
            value=value,
            metadata=metadata,
        )

    def _generate_picks(self, team_id: str) -> List[TradeAsset]:
        picks: List[TradeAsset] = []
        for round_number in range(1, 8):
            base_value = 22 - round_number * 2
            picks.append(
                TradeAsset(
                    asset_id=f"pick:{team_id}:{round_number}",
                    asset_type="pick",
                    name=f"{team_id} Round {round_number} Pick",
                    value=float(max(2.0, base_value)),
                    metadata={"round": str(round_number)},
                )
            )
        return picks

    def _find_contract(self, player_id: str, position: str):
        # search caches first
        for contracts in self._contracts_repo._cache.values():  # type: ignore[attr-defined]
            for contract in contracts:
                if contract.player_id == player_id:
                    return contract
        # fallback: scan teams
        for team in self._team_repo.list_teams():
            contracts = self._contracts_repo.list_contracts(team.team_id)
            for contract in contracts:
                if contract.player_id == player_id:
                    return contract
        return None

    # ------------------------------------------------------------------
    # Trade evaluation
    # ------------------------------------------------------------------
    def evaluate_trade(
        self,
        our_assets: Iterable[TradeAsset],
        their_assets: Iterable[TradeAsset],
    ) -> TradeEvaluation:
        our_value = sum(asset.value for asset in our_assets)
        their_value = sum(asset.value for asset in their_assets)
        diff = their_value - our_value
        total = their_value + our_value
        if total <= 0:
            balance_score = 0.5
        else:
            balance = (our_value - their_value) / total
            balance_score = max(0.0, min(1.0, 0.5 + balance / 2))
        accepted = our_value >= their_value * 0.92 if their_value > 0 else True
        if accepted:
            message = "CPU would accept this trade."
        elif diff > 0:
            message = "Add more value to match the other side."
        else:
            message = "Offer is strong; consider removing an asset."
        return TradeEvaluation(our_value, their_value, diff, accepted, message, balance_score)

    # ------------------------------------------------------------------
    # Trade execution and undo
    # ------------------------------------------------------------------
    def execute_trade(
        self,
        my_team: TeamInfo,
        other_team: TeamInfo,
        our_assets: Iterable[TradeAsset],
        their_assets: Iterable[TradeAsset],
    ) -> TradeResult:
        our_players = self._roster_repo.list_players(my_team.team_id)
        their_players = self._roster_repo.list_players(other_team.team_id)
        snapshot = {
            my_team.team_id: list(our_players),
            other_team.team_id: list(their_players),
        }

        swapped_ours, swapped_theirs, movements = self._swap_players(
            my_team.team_id,
            other_team.team_id,
            our_players,
            their_players,
            our_assets,
            their_assets,
        )
        self._roster_repo.save_roster(my_team.team_id, swapped_ours)
        self._roster_repo.save_roster(other_team.team_id, swapped_theirs)

        our_summary, their_summary = self._update_contracts_after_trade(
            my_team.team_id,
            other_team.team_id,
            movements,
        )

        evaluation = self.evaluate_trade(our_assets, their_assets)
        self._last_trade = TradeState(snapshot=snapshot, movements=movements)
        self._write_state()

        return TradeResult(
            our_team_id=my_team.team_id,
            their_team_id=other_team.team_id,
            our_summary=our_summary,
            their_summary=their_summary,
            evaluation=evaluation,
        )

    def undo_last_trade(self) -> Optional[TradeUndoResult]:
        if self._last_trade is None:
            return None

        snapshot = {
            team_id: list(players)
            for team_id, players in self._last_trade.snapshot.items()
        }
        for team_id, players in snapshot.items():
            self._roster_repo.save_roster(team_id, players)

        # revert contracts in reverse order of movements
        for movement in reversed(self._last_trade.movements):
            self._contracts_repo.transfer_contract(
                movement.player_id,
                movement.to_team,
                movement.from_team,
            )

        summaries: Dict[str, CapSummary] = {}
        for team_id in snapshot:
            summaries[team_id] = self._contracts_repo.calculate_cap_summary(team_id)

        self._last_trade = None
        self._write_state()
        return TradeUndoResult(rosters=snapshot, summaries=summaries)

    def _swap_players(
        self,
        our_team_id: str,
        their_team_id: str,
        our_players: List[RosterPlayer],
        their_players: List[RosterPlayer],
        our_assets: Iterable[TradeAsset],
        their_assets: Iterable[TradeAsset],
    ) -> tuple[List[RosterPlayer], List[RosterPlayer], List[TradeMovement]]:
        our_map = {p.player_id: p for p in our_players}
        their_map = {p.player_id: p for p in their_players}
        movements: List[TradeMovement] = []

        for asset in our_assets:
            if asset.asset_type != "player":
                continue
            player_id = asset.metadata.get("player_id")
            if player_id and player_id in our_map:
                player = our_map.pop(player_id)
                their_map[player_id] = player
                movements.append(TradeMovement(player_id, our_team_id, their_team_id))

        for asset in their_assets:
            if asset.asset_type != "player":
                continue
            player_id = asset.metadata.get("player_id")
            if player_id and player_id in their_map:
                player = their_map.pop(player_id)
                our_map[player_id] = player
                movements.append(TradeMovement(player_id, their_team_id, our_team_id))

        return list(our_map.values()), list(their_map.values()), movements

    def _update_contracts_after_trade(
        self,
        our_team_id: str,
        their_team_id: str,
        movements: List[TradeMovement],
    ) -> tuple[CapSummary, CapSummary]:
        our_summary = self._contracts_repo.calculate_cap_summary(our_team_id)
        their_summary = self._contracts_repo.calculate_cap_summary(their_team_id)
        for movement in movements:
            from_summary, to_summary = self._contracts_repo.transfer_contract(
                movement.player_id,
                movement.from_team,
                movement.to_team,
            )
            if movement.from_team == our_team_id:
                our_summary = from_summary
                their_summary = to_summary
            elif movement.from_team == their_team_id:
                their_summary = from_summary
                our_summary = to_summary
        return our_summary, their_summary

    def _write_state(self) -> None:
        if self._last_trade is None:
            self._state_path.unlink(missing_ok=True)
            return
        payload = self._last_trade.to_dict()
        try:
            self._state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:  # pragma: no cover - defensive
            LOGGER.warning("Unable to persist last-trade state")

    def load_last_trade(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            LOGGER.warning("Malformed trade state; ignoring")
            return
        if isinstance(data, dict):
            self._last_trade = TradeState.from_dict(data)
        else:
            LOGGER.warning("Unexpected trade state payload: %s", type(data))
            self._last_trade = None
