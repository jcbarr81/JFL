# Balancing Guide

The simulation targets realistic pro football rates for pace, efficiency, and volatility. This guide explains how to measure current balance and adjust tuning knobs.

## Key targets

`sim.calibration.CALIBRATION_TARGETS` defines the acceptable ranges:

- Plays per team per game: 60-75
- Completion percentage: 58-68%
- Yards per attempt: 6.0-7.8
- Pressure rate: 5-12%
- Sack rate: 5-9%
- Interception rate: 1.5-3%
- Rush yards per carry: 4.0-4.7
- Penalties per team per game: 4-9

## Running the automated calibration batch

Use `scripts/calibrate.py` to run repeated seasons and aggregate the league averages.

```powershell
python scripts/calibrate.py --seasons 5 --teams 8 --seed 123
```

The default output is a table that compares actual league averages to the target ranges. Pass `--json` to emit machine readable data (averages, target bands, and suggested tuning multipliers).

Important parameters:

- `--seasons` - Number of seasons to simulate (higher improves stability at the cost of runtime).
- `--teams` - Controls league size for calibration (default 8 mirrors the sample league).
- `--seed` - Base RNG seed. Each season increments the seed by one to diversify samples.
- `--quarter-length`, `--quarters`, `--max-plays` - Override the `GameConfig` pace assumptions if you are testing alternate rules.

## Adjusting tuning constants

Global tuning multipliers live in `sim/ruleset.py` within the `TUNING` object:

- `completion_mod`
- `pressure_mod`
- `sack_distance`
- `int_mod`
- `yac_mod`
- `rush_block_mod`
- `penalty_rate_mod`

The calibration report includes `suggestions` that gently scale each multiplier toward the midpoint of the target band. Apply changes in small increments, rerun calibration, and repeat until the averages sit inside the desired ranges.

Example workflow:

1. Run `python scripts/calibrate.py --seasons 10 --json > build/calibration.json`.
2. Inspect the `suggestions` block and update the corresponding attributes on `TUNING`.
3. Commit the tuning change along with the calibration artifact or summary.
4. Re-run the batch to confirm the adjustments hold with fresh seeds.

## Manual spot checks

Automated calibration is a coarse guide; supplement it with targeted simulations:

- Single game: `POST /game/simulate` with different team matchups and seeds.
- Full season exports: `python scripts/run_season.py --seed 99` (stats land in `build/season/`).
- Regression tests: `pytest` (unit coverage on tackle/momentum, statbook reconciliation, etc.).

Capture interesting savepoints with `domain.savepoint.create_savepoint("tag")` so you can rerun specific leagues after tweaking parameters.

## Best practices

- Change one multiplier at a time and keep notes on the rationale.
- Keep the sample league deterministic (`scripts/seed_league.py --seed <value>`) so you can isolate tuning effects.
- When metrics fall outside the target band, prefer adjusting the dedicated knob rather than piling compensating tweaks elsewhere.
- After large changes, simulate multiple seasons and compare distribution spreads (available in the calibration JSON under `metric_spreads`).
