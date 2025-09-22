from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from domain.contracts import CAP_LIMIT, ContractsRepository


def test_contract_repository_generates_and_updates(tmp_path: Path) -> None:
    repo = ContractsRepository(tmp_path)

    contracts = repo.list_contracts("ATX")
    assert contracts, "Expected generated contracts"

    original_summary = repo.calculate_cap_summary("ATX")
    first = contracts[0]
    lowered = replace(first, base_salary=max(500_000.0, first.base_salary * 0.9))
    summary = repo.update_contract(lowered)
    assert summary.cap_available <= summary.cap_limit

    export_path = repo.export_cap_table("ATX")
    assert export_path.exists()

    restructure_summary = repo.auto_restructure("ATX")
    assert restructure_summary.cap_limit == CAP_LIMIT
