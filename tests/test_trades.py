from __future__ import annotations

import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from domain.trades import TradeAsset, TradeRepository
from domain.teams import TeamInfo


def _trade_asset(asset_id: str, value: float) -> TradeAsset:
    return TradeAsset(
        asset_id=asset_id,
        asset_type="player",
        name=asset_id,
        value=value,
        metadata={"player_id": asset_id},
    )


def test_evaluate_trade_balance(tmp_path: Path) -> None:
    repo = TradeRepository(tmp_path)
    even = repo.evaluate_trade([_trade_asset("a", 10.0)], [_trade_asset("b", 10.0)])
    assert even.accepted is True
    assert pytest.approx(0.5, rel=1e-3) == even.balance_score

    lopsided = repo.evaluate_trade([_trade_asset("a", 8.0)], [_trade_asset("b", 16.0)])
    assert lopsided.accepted is False
    assert lopsided.balance_score < 0.5
    assert lopsided.diff > 0


def test_execute_and_undo_trade(tmp_path: Path) -> None:
    user_home = tmp_path / "user"
    settings_dir = user_home / "settings"
    settings_dir.mkdir(parents=True, exist_ok=True)

    rosters_path = settings_dir / "rosters.json"
    rosters_path.write_text(
        json.dumps(
            {
                "NYG": [
                    {
                        "player_id": "nyg_qb1",
                        "name": "Giants QB",
                        "position": "QB",
                        "jersey_number": 10,
                        "overall": 86,
                    }
                ],
                "DAL": [
                    {
                        "player_id": "dal_qb1",
                        "name": "Cowboys QB",
                        "position": "QB",
                        "jersey_number": 4,
                        "overall": 89,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    contracts_path = settings_dir / "contracts.json"
    contracts_path.write_text(
        json.dumps(
            {
                "NYG": [
                    {
                        "contract_id": "c-nyg-qb1",
                        "player_id": "nyg_qb1",
                        "team_id": "NYG",
                        "player_name": "Giants QB",
                        "position": "QB",
                        "years": 3,
                        "base_salary": 12_000_000,
                        "signing_bonus": 6_000_000,
                        "signing_year": 2024,
                        "status": "Active",
                    }
                ],
                "DAL": [
                    {
                        "contract_id": "c-dal-qb1",
                        "player_id": "dal_qb1",
                        "team_id": "DAL",
                        "player_name": "Cowboys QB",
                        "position": "QB",
                        "years": 4,
                        "base_salary": 18_000_000,
                        "signing_bonus": 8_000_000,
                        "signing_year": 2024,
                        "status": "Active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    repo = TradeRepository(user_home)

    contracts_repo = repo._contracts_repo  # type: ignore[attr-defined]

    def _persist_stub(team_id: str, contracts) -> None:
        data = {}
        if contracts_repo._fallback_path.exists():  # type: ignore[attr-defined]
            data = json.loads(contracts_repo._fallback_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
        data[team_id] = [contract.to_dict() for contract in contracts]
        contracts_repo._fallback_path.write_text(json.dumps(data, indent=2), encoding="utf-8")  # type: ignore[attr-defined]

    contracts_repo._persist_bulk = _persist_stub  # type: ignore[assignment]

    nyg = TeamInfo(team_id="NYG", name="Giants", city="New York", abbreviation="NYG")
    dal = TeamInfo(team_id="DAL", name="Cowboys", city="Dallas", abbreviation="DAL")

    our_asset = next(
        asset for asset in repo.list_assets("NYG")["players"] if asset.metadata.get("player_id") == "nyg_qb1"
    )
    their_asset = next(
        asset for asset in repo.list_assets("DAL")["players"] if asset.metadata.get("player_id") == "dal_qb1"
    )

    result = repo.execute_trade(nyg, dal, [our_asset], [their_asset])
    state_path = settings_dir / "trade_state.json"
    assert state_path.exists()

    nyg_players_after = {player.player_id for player in repo._roster_repo.list_players("NYG")}
    dal_players_after = {player.player_id for player in repo._roster_repo.list_players("DAL")}
    assert "dal_qb1" in nyg_players_after
    assert "nyg_qb1" in dal_players_after

    undo = repo.undo_last_trade()
    assert undo is not None
    assert state_path.exists() is False

    nyg_players_restored = {player.player_id for player in repo._roster_repo.list_players("NYG")}
    dal_players_restored = {player.player_id for player in repo._roster_repo.list_players("DAL")}
    assert nyg_players_restored == {"nyg_qb1"}
    assert dal_players_restored == {"dal_qb1"}
    assert set(undo.summaries.keys()) == {"NYG", "DAL"}
    assert repo.undo_last_trade() is None
