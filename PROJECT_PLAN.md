# Gridiron Sim – Project Plan

**Last updated:** 2025‑09‑19  
**Target platform:** Windows 11  
**Primary stack:** Python 3.11+, FastAPI, SQLModel/SQLAlchemy, Pydantic, NumPy, PyQt6/PySide6 (for Play Editor), pytest  
**Build goals:** Single‑player league sim, multi‑season, yearly draft class generation, user‑drawn plays with logic, realistic stats, reproducible simulations.

---

## Table of Contents

1. [Objectives, Non‑Goals, and Realism Targets](#objectives-non-goals-and-realism-targets)  
2. [Cross‑Cutting Definition of Done](#cross-cutting-definition-of-done)  
3. [Step‑by‑Step Plan (Ordered)](#step-by-step-plan-ordered)  
   - [1) Environment & Tooling](#1-environment--tooling)  
   - [2) Minimal FastAPI App](#2-minimal-fastapi-app)  
   - [3) Domain Models & Persistence](#3-domain-models--persistence)  
   - [4) Seed Script: Tiny League](#4-seed-script-tiny-league)  
   - [5) Play JSON Schema + Validator](#5-play-json-schema--validator)  
   - [6) Engine MVP: Tick Loop & Kinematics](#6-engine-mvp-tick-loop--kinematics)  
   - [7) Event Log & StatBook](#7-event-log--statbook)  
   - [8) Game Flow & Ruleset](#8-game-flow--ruleset)  
   - [9) Playcalling (Rule‑Based v1)](#9-playcalling-rule-based-v1)  
   - [10) Season & Scheduler](#10-season--scheduler)  
   - [11) Draft Class Generation](#11-draft-class-generation)  
   - [12) Fatigue & Injuries](#12-fatigue--injuries)  
   - [13) Penalties & Special Teams](#13-penalties--special-teams)  
   - [14) Calibration & Balancing Layer](#14-calibration--balancing-layer)  
   - [15) Play Editor (PyQt6/PySide6) MVP](#15-play-editor-pyqt6pyside6-mvp)  
   - [16) Public API Surface](#16-public-api-surface)  
   - [17) Performance & Parallelization](#17-performance--parallelization)  
   - [18) Save/Load, Exports, Determinism](#18-saveload-exports-determinism)  
   - [19) Documentation Set](#19-documentation-set)  
   - [20) Optional Windows Packaging](#20-optional-windows-packaging)  
4. [Sanity Gates (Milestone Tests)](#sanity-gates-milestone-tests)  
5. [Codex Prompting Playbook](#codex-prompting-playbook)  
6. [Risk Register & Mitigations](#risk-register--mitigations)  
7. [Deliverable Checklist](#deliverable-checklist)  
8. [Appendix: Commands & File Layout](#appendix-commands--file-layout)

---

## Objectives, Non‑Goals, and Realism Targets

### Objectives
- Create/manage a league and simulate **multiple seasons** with standings and stats.
- **Generate new players** each year for a draft; integrate rookies into rosters.
- **Draw plays** in an editor; serialize to JSON; engine executes those assignments.
- Produce **realistic, tunable** team and player stats.
- Deterministic execution with seeds for testability and balancing.

### Non‑Goals (Initial Phases)
- 3D graphics or advanced rendering.
- Online multiplayer.
- Full CBA/cap realism (start simple; add later).

### “Realistic” Statistical Targets (initial)
- Plays per team per game: **60–75**  
- Pass completion rate: **58–68%**  
- Yards per attempt: **6.0–7.8**  
- Sack rate: **5–9%** of dropbacks  
- INT rate: **1.5–3%** of attempts  
- Rush YPC: **4.0–4.7**  
- Penalties/team: **4–9**  
- Injury incidence (any): **0.7–1.5 players/game**

---

## Cross‑Cutting Definition of Done

For **every** step below, it is Done when:
- �... Code formatted (black), lint‑clean (ruff), typed (mypy)  
- �... Unit tests added/updated; `pytest` passes  
- �... Public functions have docstrings and/or docs updated  
- �... Determinism preserved where claimed  
- �... No behavior‑affecting TODOs remain

---

## Step‑by‑Step Plan (Ordered)

### 1) Environment & Tooling

**Do**
- Install Python 3.11+, VS Code + Python extension + Git.  
- Create repo, virtual env, and install base deps.

**Commands**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install fastapi uvicorn[standard] sqlmodel sqlalchemy pydantic orjson numpy pytest pytest-cov ruff black mypy typer pyqt6
pip install python-multipart
```

**Acceptance Criteria**
- `python --version` shows **3.11+**  
- `pytest -q` runs (0 tests ok)  
- Git repo initialized, `.venv/` in `.gitignore`

**Example Codex Prompt**
> Create a `pyproject.toml` for black, ruff, and mypy (Python 3.11). Use strict mypy where practical and set reasonable ruff rules.

---

### 2) Minimal FastAPI App

**Do**
- `app/main.py` with `/health` and `/version`; enable CORS for localhost; add reload setup.

**Acceptance Criteria**
- `uvicorn app.main:app --reload` starts  
- `GET /health` → `{"ok": true}`  
- `GET /version` → `"0.1.0"`

**Example Codex Prompt**
> In `app/main.py`, scaffold FastAPI with `/health` and `/version`. Add CORS for `http://localhost:*`.

---

### 3) Domain Models & Persistence

**Do**
- Pydantic models: `Attributes`, `Player`, `Team`, `Play`, `RoutePoint`, `Assignment`, `GameState`.  
- SQLModel tables: `PlayerRow`, `TeamRow`, `GameRow`, `SeasonRow`, `BoxScoreRow`, `EventRow`, `DraftProspectRow`.  
- `domain/db.py`: engine, session helpers, `create_all()`.

**Acceptance Criteria**
- Running `create_all()` generates `gridiron.db`.  
- Insert/query `TeamRow` and `PlayerRow` in a smoke test.

**Example Codex Prompts**
> In `domain/models.py`, implement Pydantic models for a football sim with type hints and Literals for positions.

> In `domain/db.py`, implement SQLite engine `sqlite:///gridiron.db`, `get_session()` context manager, and `create_all()`.

---

### 4) Seed Script: Tiny League

**Do**
- `scripts/seed_league.py` creates 4–8 teams and rosters with plausible attributes.  
- Save 2–3 sample plays (JSON) in `data/plays/`.

**Acceptance Criteria**
- Running the script inserts teams/players; DB shows expected counts.  
- Sample plays are present and loadable.

**Example Codex Prompt**
> Write `scripts/seed_league.py` to create 4 teams × 40 players with plausible attributes and commit to DB. Log created IDs.

---

### 5) Play JSON Schema + Validator

**Do**
- Canonical play JSON (formation, personnel, assignments, routes with time‑ordered waypoints).  
- `POST /play/validate` to check role count, monotonic `t`, required assignments.

**Acceptance Criteria**
- Valid play (e.g., Slant Flat R) returns `{ok:true}`.  
- Invalid plays return 400 with error details.

**Example Codex Prompt**
> Implement `POST /play/validate` in `app/api/plays.py`. Use Pydantic schemas; return errors with fields and messages.

---

### 6) Engine MVP: Tick Loop & Kinematics

**Do**
- `sim/engine.py`: 20 Hz tick loop, simple acceleration cap, fatigue scalar.  
- Implement basic **run/pass** primitives: ball flight with accuracy cone, catch/contest, tackle with `tak` vs `btk`, angle, and relative speed.

**Acceptance Criteria**
- `simulate_play()` runs < ~200 ms for 22 entities × 8 s.  
- Deterministic with seed.  
- Returns `PlayResult` (`type`, `air_yards`, `yac`, `pressure`, `sack`, `int`, …).

**Example Codex Prompts**
> In `sim/engine.py`, implement `simulate_play(play, offense_state, defense_state, seed)` at 20 Hz with deterministic RNG.

> Implement `tackle_success(def_attr, bc_attr, angle_deg, rel_speed)->bool` with ~65% baseline when skills equal; unit tests included.

---

### 7) Event Log & StatBook

**Do**
- `sim/statbook.py`: append events (`snap`, `throw`, `catch`, `tackle`, `sack`, `penalty`, …).  
- Reducers → box scores and advanced rates (EPA/play, success%, pressure%).

**Acceptance Criteria**
- Events from plays reduce to consistent player/team box scores.  
- Tests verify attempts, completions, sacks, INTs reconciliation.

**Example Codex Prompt**
> Implement `StatBook.note(evt)` and reducers `boxscore()` and `advanced_rates()`. Add tests for stat consistency.

---

### 8) Game Flow & Ruleset

**Do**
- `sim/ruleset.py`: downs, distance, yardline, first downs, quarter transitions, OT basics, timeouts.  
- `simulate_game(teamA, teamB, bookA, bookB, seed)` loops ~120 plays with playcalling.

**Acceptance Criteria**
- Game completes with final score, drive chart, team & player box scores.  
- No impossible states; clock and yardline valid; deterministic with seed.

**Example Codex Prompt**
> Implement `simulate_game(...)` handling sequencing, scoring, kickoffs, punts (stubs ok), and returns drive chart and stats.

---

### 9) Playcalling (Rule‑Based v1)

**Do**
- `sim/ai_decision.py`: rules by down/distance/field position/clock/score.  
- Defensive shell selection (front, coverage family, blitz rate).

**Acceptance Criteria**
- 3rd & long → pass rate > 75%; 3rd & short → run rate > 60%.  
- Two‑minute offense trends pass/out‑of‑bounds.

**Example Codex Prompt**
> Implement `call_offense(gs, playbook)` with weighted rules and tests asserting distributions for common situations.

---

### 10) Season & Scheduler

**Do**
- `sim/schedule.py`: round‑robin or NFL‑like schedule generator.  
- `scripts/run_season.py`: drive game‑by‑game; produce standings and CSV exports.

**Acceptance Criteria**
- Full season completes; W‑L reflects game outcomes.  
- `player_stats.csv`, `team_stats.csv`, `standings.csv` written.

**Example Codex Prompt**
> Implement `make_schedule(teams)->list[(week, home_id, away_id)]` with home/away balance; add fairness tests.

---

### 11) Draft Class Generation

**Do**
- `sim/draft.py`: archetype‑based distributions per position; hidden true ratings; scouting noise; combine metrics.  
- Draft (snake order), rookies added to depth charts; simple contracts.

**Acceptance Criteria**
- Yearly draft class (~250 players) generated; teams draft successfully.  
- Rookies integrated; rosters updated.

**Example Codex Prompt**
> Implement `generate_draft_class(year, size_by_pos)`, `scouting_view(prospect, noise_level)`, and tests for distributions and noise.

---

### 12) Fatigue & Injuries

**Do**
- Per‑snap fatigue increments, recovery between drives; substitution triggers.  
- Injury checks on high‑impact events; severity tier → out for plays/games/weeks.

**Acceptance Criteria**
- Fatigue reduces speed on long drives; subs can occur.  
- Injury rates within target band; injuries persisted and respected.

**Example Codex Prompt**
> Implement `apply_fatigue(entity, snap_load)` and `check_injury(event, attrs, impact)`. Add Monte Carlo tests across 10k plays to verify rates.

---

### 13) Penalties & Special Teams

**Do**
- Penalty events (offsides, holding, DPI) with frequencies & enforcement.  
- Field goals with distance‑dependent curve.  
- Punts/kickoffs with returns.

**Acceptance Criteria**
- Penalties/team: 4–9 per game.  
- FG success: ~90% (<40 yds), 70–85% (40–49), 55–75% (50+), tunable.

**Example Codex Prompt**
> Implement `attempt_field_goal(yardline, k_attr)` and `apply_penalty(gs, penalty_type)`, with tests for enforcement logic.

---

### 14) Calibration & Balancing Layer

**Do**
- Centralize modifiers in `sim/ruleset.py`: `completion_mod`, `pressure_mod`, `int_mod`, `yac_mod`, `rush_block_mod`, `penalty_rate_mod`, …  
- `scripts/calibrate.py`: batch sims reporting league averages vs. targets; small auto‑tuning.

**Acceptance Criteria**
- After tuning, season averages fall within target bands across multiple seeds.

**Example Codex Prompt**
> Create `scripts/calibrate.py` that runs 5 seasons, reports deltas vs. targets, and proposes bounded (±10%) multiplier adjustments.

---

### 15) Play Editor (PyQt6/PySide6) MVP

**Do**
- QGraphicsScene grid in yards.  
- Drag 11 offensive tokens; assign roles; draw waypoints with time.  
- Mirror (L/R), hash‑side behavior; save/load `data/plays/*.json`.  
- Validation before save.

**Acceptance Criteria**
- Can create and mirror “Slant Flat R”; validation passes; engine runs it.

**Example Codex Prompt**
> Build a `PlayEditor` with field canvas, draggable players, waypoint editing, and menu actions: New, Open, Save, Mirror, Validate. Serialize to the Play JSON schema.

---

### 16) Public API Surface

**Do**
- Endpoints:  
  - `POST /league/new`  
  - `POST /season/run` (seeds, parallel workers)  
  - `POST /game/simulate`  
  - `GET /stats/team/{id}`  
  - `GET /stats/player/{id}`  
  - `POST /play/import`  
  - `GET /play/list`  
- OpenAPI tags and concise schemas.

**Acceptance Criteria**
- Happy path returns 2xx with valid bodies; `/docs` renders; error paths return structured 4xx/5xx.

**Example Codex Prompt**
> Implement the listed routes with dependency‑injected DB sessions and typed request/response models; tag endpoints and add descriptions.

---

### 17) Performance & Parallelization

**Do**
- Profile with `cProfile`; vectorize small math with NumPy when simple.  
- Parallelize season sims per game (multiprocessing/joblib).  
- Compress event logs (`orjson`, optionally `zstandard`).

**Acceptance Criteria**
- Season run scales near‑linearly by core count for independent games.  
- Single game runtime acceptable on mid‑range desktop.

**Example Codex Prompt**
> Profile `simulate_game` and refactor top 15 cumulative functions for clarity and speed; keep code readable.

---

### 18) Save/Load, Exports, Determinism

**Do**
- Savepoints at **preseason**, **mid‑season**, **pre‑draft**.  
- CSV/JSON export: player stats, team stats, standings, draft results, injuries.  
- Seed mapping from `(season, week, home_id, away_id)`.

**Acceptance Criteria**
- Reloading a savepoint and re‑running with same seeds yields identical outcomes.  
- CSVs open in Excel with headers and correct types.

**Example Codex Prompt**
> Implement a deterministic SeedManager that maps `(season, week, home_id, away_id)` → `seed:int`. Add tests asserting identical outcomes across runs.

---

### 19) Documentation Set

**Do**
- `README.md`: quickstart, concepts, commands.  
- `docs/PLAY_FORMAT.md`: JSON schema and examples.  
- `docs/BALANCING.md`: calibration guide.  
- Provide tiny sample league and four sample plays.

**Acceptance Criteria**
- New dev can clone → seed → simulate a game → view box score by following README only.

**Example Codex Prompt**
> Draft a concise `README.md` with setup, seed, run single game, and creating a new play in the editor.

---

### 20) Optional Windows Packaging

**Do**
- PyInstaller spec for desktop executable: launcher GUI for (a) season run, (b) play editor.  
- Bundle `data/plays/` and default DB template; user data to `%LOCALAPPDATA%/GridironSim/`.

**Acceptance Criteria**
- Double‑clickable `.exe` runs on Windows 11 without dev tools.

**Example Codex Prompt**
> Provide a PyInstaller spec to build `GridironSim.exe`, bundling the play editor and assets, writing DB to `%LOCALAPPDATA%/GridironSim/`.

---

## Sanity Gates (Milestone Tests)

1. **Play Sim Sanity** – 1,000 slant‑flat plays: completion 60–75%, INT 1–3%, sack 3–8%.  
2. **Full Game** – 120 plays, no clock/yard anomalies; totals reconcile; box score consistent.  
3. **Season Stability** – Full round‑robin completes; standings match game results; no crashes.  
4. **Calibration** – League averages fall within targets after sliders tuned.  
5. **Draft Loop** – Year rolls, rookies drafted, injuries reset, schedule regenerates.

---

## Codex Prompting Playbook

**Pattern: Test‑First, Small Functions, Clear Constraints**

**General Template**
```python
# Context: sim/engine.py
# Goal: Implement tackle_success with attributes-based probability.
# Constraints:
# - Use tak vs btk diff, approach angle (0° head-on best), relative speed.
# - Baseline 0.65 at equal skills, ~30° approach, logistic scaling.
# - < 40 lines, stdlib only, deterministic with seeded RNG.
# Tests: see tests/test_tackle.py expected rates.

def tackle_success(...):
    ...
```
**Refactor Prompt**
> Refactor `simulate_play` into helpers: target selection, movement, contact resolution, event emission. Preserve behavior. Add type hints and tests for helpers.

**UI Prompt**
> In `ui/play_editor/editor.py`, add “Mirror Left/Right” that reflects x‑coordinates across midfield. Keep time values unchanged. Update validation accordingly.

**API Prompt**
> In `app/api/games.py`, implement `POST /game/simulate` to accept team IDs and a seed, run a game, persist results, and return summary with final score, drive chart, and top performers.

**Calibration Prompt**
> Given observed stats vs. target bands, compute deltas and propose bounded (±10%) adjustments for completion%, pressure%, int%, yac%, and rush_block%.

---

## Risk Register & Mitigations

- **Scope creep** → Gate advanced features behind flags; prioritize MVP.  
- **Performance bottlenecks** → Profile first; parallelize per‑game; avoid premature micro‑opts.  
- **Realism drift** → Centralize sliders; run calibration after engine changes.  
- **Data integrity** → Strong schemas; test save/load determinism; migrations as needed.  
- **UI friction** → Editor stays minimal and schema‑first; validation before save.

---

## Deliverable Checklist

- [ ] Tooling & repo scaffold  
- [ ] Health endpoints  
- [ ] Domain models (Pydantic)  
- [ ] DB schema (SQLModel) + seed script  
- [ ] Play schema & validator (API)  
- [ ] Engine tick loop + movement  
- [ ] Pass/run outcomes + tackle logic  
- [ ] Event log + StatBook reducers  
- [ ] Game flow + ruleset  
- [ ] Rule‑based playcalling  
- [ ] Scheduler + season runner + exports  
- [ ] Draft class + rookie integration  
- [ ] Fatigue + injuries  
- [ ] Penalties + special teams  
- [ ] Calibration layer + batch sims  
- [ ] Play editor MVP  
- [ ] Public API surface  
- [ ] Performance pass + parallelization  
- [ ] Save/Load + determinism  
- [ ] Documentation set  
- [ ] Optional Windows packaging

---

## Appendix: Commands & File Layout

**Common Commands**
```powershell
# Run API (dev)
uvicorn app.main:app --reload

# Run tests
pytest -q

# Lint & format
ruff check .
black .
mypy .

# Seed a tiny league
python scripts/seed_league.py

# Run a quick single game (to be added)
python scripts/run_game.py --home TEAM_A --away TEAM_B --seed 42
```

**Suggested File Layout**
```
gridiron-sim/
  app/
    main.py
    api/
      plays.py
      games.py
      league.py
      stats.py
  domain/
    models.py
    db.py
  sim/
    engine.py
    ruleset.py
    ai_decision.py
    draft.py
    schedule.py
    statbook.py
    fatigue.py
    injury.py
  ui/
    play_editor/
      editor.py
  data/
    plays/
    league_templates/
  scripts/
    seed_league.py
    run_season.py
    calibrate.py
  tests/
  docs/
    PLAY_FORMAT.md
    BALANCING.md
  pyproject.toml
  README.md
```
---

**Notes**
- Store long‑lived entities (players, teams, seasons, games, box scores) in SQL; store **plays** as JSON on disk and register in DB for versioning.
- Use deterministic seeds per `(season, week, home_id, away_id)` to ensure reproducibility.

