#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from sim.calibration import CALIBRATION_TARGETS, run_calibration
from sim.ruleset import GameConfig, TUNING


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run calibration batch simulations")
    parser.add_argument("--seasons", type=int, default=5, help="Number of seasons to simulate")
    parser.add_argument("--teams", type=int, default=8, help="Number of teams in the generated league")
    parser.add_argument("--seed", type=int, default=0, help="Base RNG seed")
    parser.add_argument("--quarter-length", type=float, default=900.0, help="Length of each quarter in seconds")
    parser.add_argument("--quarters", type=int, default=4, help="Number of regulation quarters")
    parser.add_argument("--max-plays", type=int, default=130, help="Maximum plays per game before simulation stops")
    parser.add_argument("--json", action="store_true", help="Emit machine readable JSON output")
    return parser.parse_args()


def _run(args: argparse.Namespace) -> dict:
    config = GameConfig(
        quarter_length=args.quarter_length,
        quarters=args.quarters,
        max_plays=args.max_plays,
    )
    report = run_calibration(
        seasons=args.seasons,
        team_count=args.teams,
        base_seed=args.seed,
        config=config,
    )
    return {
        "parameters": {
            key: getattr(TUNING, key)
            for key in ("completion_mod", "pressure_mod", "sack_distance", "int_mod", "yac_mod", "rush_block_mod", "penalty_rate_mod")
        },
        "targets": CALIBRATION_TARGETS,
        "averages": report.league_averages,
    }


def _print_table(data: dict) -> None:
    metrics = data["averages"]
    keys = list(CALIBRATION_TARGETS.keys())
    header = f"{'Metric':<20}{'Actual':>12}{'Target':>18}"
    print(header)
    print("-" * len(header))
    for key in keys:
        actual = metrics.get(key, 0.0)
        target = CALIBRATION_TARGETS.get(key)
        target_str = f"{target[0]:.2f}-{target[1]:.2f}"
        print(f"{key:<20}{actual:>12.3f}{target_str:>18}")


def main() -> None:
    args = _parse_args()
    output = _run(args)
    if args.json:
        print(json.dumps(output, indent=2))
        return
    _print_table(output)


if __name__ == "__main__":
    main()
