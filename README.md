# Gridiron Sim

Gridiron Sim is a deterministic American football league simulator built with FastAPI, SQLModel, and a physics-lite Python engine. It ships with a tiny sample league, a handful of reference plays, and tooling for season simulations and balancing.

## Quickstart (Windows PowerShell)

1. Clone this repository and open a terminal at its root.
2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
   On macOS/Linux use `python3 -m venv .venv` then `source .venv/bin/activate`.
3. Install dependencies:
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Seed the sample league

`gridiron.db` already contains four seeded teams (ATX, BOS, CHI, DEN). To rebuild deterministically, run:

```powershell
python scripts/seed_league.py
```

The script reseeds the SQLite database and refreshes sample plays under `data/plays/`.

## Run the API

```powershell
uvicorn app.main:app --reload
```

The app creates any missing tables on boot. Visit http://127.0.0.1:8000/docs for interactive OpenAPI docs or call the health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Simulate a game

With the server running and the sample league seeded, you can simulate ATX vs BOS:

```powershell
$body = @{
  home_team_id = "ATX"
  away_team_id = "BOS"
  seed = 42
  save = $true
}
Invoke-RestMethod -Uri http://127.0.0.1:8000/game/simulate `
  -Method Post `
  -Body ($body | ConvertTo-Json) `
  -ContentType "application/json" |
  ConvertTo-Json -Depth 5
```

On macOS/Linux you can use `curl`:

```bash
curl -X POST http://127.0.0.1:8000/game/simulate \
  -H "Content-Type: application/json" \
  -d '{"home_team_id":"ATX","away_team_id":"BOS","seed":42,"save":true}' | jq
```

The response includes the scores, drive summaries, and a `boxscore` object (team and player stats). Because `save` is true, the game is persisted to `gridiron.db`. Fetch aggregated stats at `GET /stats/team/ATX`, `GET /stats/player/ATX-QB01`, or list plays with `GET /play/list`.

## Explore the sample assets

- League database: `gridiron.db` (SQLite, seeded with 4 x 40-player rosters).
- Plays: `data/plays/*.json` (offense, defense, and special teams examples).
- Savepoints: `domain.savepoint.create_savepoint("name")` copies the DB and assets under `data/savepoints/<name>/`.

## Useful scripts

- `python scripts/seed_league.py --seed 20250919` - regenerate the sample league and play files.
- `python scripts/run_season.py --seed 1` - simulate an eight-team season and export CSV/JSON summaries to `build/season/`.
- `python scripts/calibrate.py --seasons 8` - batch-run calibration and print league averages (see `docs/BALANCING.md`).

## Testing and quality gates

Run the standard checks from an activated environment:

```powershell
pytest
ruff check .
black --check .
mypy .
```

## Project layout

- `app/` - FastAPI routers (`/league`, `/season`, `/game`, `/stats`, `/play`).
- `domain/` - Pydantic models, SQLModel tables, persistence helpers, savepoints.
- `sim/` - Core simulation engine, ruleset, scheduling, exports, calibration logic.
- `scripts/` - Command-line entry points for seeding, calibration, and season runs.
- `data/` - Sample plays and savepoint snapshots.

## Further documentation

See `docs/PLAY_FORMAT.md` for authoring JSON plays and `docs/BALANCING.md` for tuning guidance and interpreting calibration runs.
See `docs/PACKAGING_WINDOWS.md` for building the Windows launcher executable.
