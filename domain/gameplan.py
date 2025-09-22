from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from domain.teams import TeamInfo, TeamRepository

_DEFAULT_SITUATIONS: List[tuple[str, str, str]] = [
    ("1st & 10", "Inside Zone 11", "Motion to Trips"),
    ("2nd & Medium", "Play-Action Crossers", "RB Screen"),
    ("3rd & Long", "Mesh Switch", "Flood Concept"),
    ("Red Zone", "Tight Bunch Spacing", "Fade/Slant"),
    ("Two-Minute", "Quick Outs", "Seam Alert"),
    ("Goal Line", "Power Iso", "Boot Fake"),
]


@dataclass
class GameplanTendencies:
    """High-level play-calling sliders for a single gameplan."""

    run_rate: int = 52
    deep_shot_rate: int = 38
    blitz_rate: int = 26
    zone_rate: int = 62

    def clamp(self) -> None:
        self.run_rate = int(min(max(self.run_rate, 0), 100))
        self.deep_shot_rate = int(min(max(self.deep_shot_rate, 0), 100))
        self.blitz_rate = int(min(max(self.blitz_rate, 0), 100))
        self.zone_rate = int(min(max(self.zone_rate, 0), 100))

    def to_dict(self) -> Dict[str, int]:
        self.clamp()
        return {
            "run_rate": self.run_rate,
            "deep_shot_rate": self.deep_shot_rate,
            "blitz_rate": self.blitz_rate,
            "zone_rate": self.zone_rate,
        }

    @staticmethod
    def from_dict(payload: Dict[str, int]) -> "GameplanTendencies":
        return GameplanTendencies(
            run_rate=int(payload.get("run_rate", 52)),
            deep_shot_rate=int(payload.get("deep_shot_rate", 38)),
            blitz_rate=int(payload.get("blitz_rate", 26)),
            zone_rate=int(payload.get("zone_rate", 62)),
        )


@dataclass
class SituationTendency:
    """Preferred calls for a down & distance bucket."""

    bucket: str
    primary_call: str
    secondary_call: str
    notes: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "bucket": self.bucket,
            "primary_call": self.primary_call,
            "secondary_call": self.secondary_call,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(payload: Dict[str, str]) -> "SituationTendency":
        return SituationTendency(
            bucket=str(payload.get("bucket", "")),
            primary_call=str(payload.get("primary_call", "")),
            secondary_call=str(payload.get("secondary_call", "")),
            notes=str(payload.get("notes", "")),
        )


@dataclass
class WeeklyGameplan:
    """Complete weekly strategy for a given opponent."""

    team_id: str
    opponent_id: str
    week: int
    tendencies: GameplanTendencies = field(default_factory=GameplanTendencies)
    situations: List[SituationTendency] = field(default_factory=list)
    notes: str = ""
    last_modified: datetime = field(default_factory=datetime.utcnow)
    last_execution: GameplanExecution | None = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "team_id": self.team_id,
            "opponent_id": self.opponent_id,
            "week": self.week,
            "tendencies": self.tendencies.to_dict(),
            "situations": [item.to_dict() for item in self.situations],
            "notes": self.notes,
            "last_modified": self.last_modified.isoformat(),
        }
        if self.last_execution is not None:
            payload["last_execution"] = self.last_execution.to_dict()
        return payload

    @staticmethod
    def from_dict(payload: Dict[str, object]) -> "WeeklyGameplan":
        tendency_payload = payload.get("tendencies", {})
        situations_payload = payload.get("situations", [])
        notes = payload.get("notes", "")
        raw_timestamp = payload.get("last_modified")
        timestamp: datetime
        if isinstance(raw_timestamp, str):
            try:
                timestamp = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()
        execution_payload = payload.get("last_execution")
        execution = None
        if isinstance(execution_payload, dict):
            execution = GameplanExecution.from_dict(execution_payload)
        plan = WeeklyGameplan(
            team_id=str(payload.get("team_id", "")),
            opponent_id=str(payload.get("opponent_id", "")),
            week=int(payload.get("week", 1)),
            tendencies=GameplanTendencies.from_dict(tendency_payload if isinstance(tendency_payload, dict) else {}),
            situations=[
                SituationTendency.from_dict(item)
                for item in situations_payload
                if isinstance(item, dict)
            ],
            notes=str(notes),
            last_modified=timestamp,
            last_execution=execution,
        )
        return plan


@dataclass(frozen=True)
class GameplanPreview:
    """Result of a quick Monte Carlo-style tendency preview."""

    drives: int
    expected_run_calls: int
    expected_pass_calls: int
    expected_deep_shots: int
    expected_blitz_calls: int
    expected_zone_calls: int
    explosive_play_chance: float
    takeaway_chance: float
    expected_points: float


@dataclass(frozen=True)
class GameplanComparison:
    """Difference between planned tendencies and actual results."""

    run_delta: float
    deep_delta: float
    blitz_delta: float
    zone_delta: float

    def summary(self) -> str:
        focus = []
        if abs(self.run_delta) > 5:
            focus.append("Run mix")
        if abs(self.deep_delta) > 5:
            focus.append("Shot selection")
        if abs(self.blitz_delta) > 5:
            focus.append("Pressure rate")
        if abs(self.zone_delta) > 5:
            focus.append("Coverage calls")
        if not focus:
            return "Plan matched on-field tendencies."
        return "Adjust: " + ", ".join(focus)




@dataclass(frozen=True)
class GameplanExecution:
    actual: Dict[str, float]
    comparison: GameplanComparison
    recorded_at: datetime

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "actual": {key: float(value) for key, value in self.actual.items()},
            "comparison": {
                "run_delta": float(self.comparison.run_delta),
                "deep_delta": float(self.comparison.deep_delta),
                "blitz_delta": float(self.comparison.blitz_delta),
                "zone_delta": float(self.comparison.zone_delta),
                "summary": self.comparison.summary(),
            },
            "recorded_at": self.recorded_at.isoformat(),
        }
        return payload

    @staticmethod
    def from_dict(payload: Dict[str, object]) -> "GameplanExecution":
        actual_payload = payload.get("actual")
        actual: Dict[str, float] = {}
        if isinstance(actual_payload, dict):
            for key, value in actual_payload.items():
                try:
                    actual[str(key)] = float(value)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    actual[str(key)] = 0.0
        comparison_payload = payload.get("comparison")
        if isinstance(comparison_payload, dict):
            comparison = GameplanComparison(
                run_delta=float(comparison_payload.get("run_delta", 0.0)),
                deep_delta=float(comparison_payload.get("deep_delta", 0.0)),
                blitz_delta=float(comparison_payload.get("blitz_delta", 0.0)),
                zone_delta=float(comparison_payload.get("zone_delta", 0.0)),
            )
        else:
            comparison = GameplanComparison(0.0, 0.0, 0.0, 0.0)
        recorded_raw = payload.get("recorded_at")
        if isinstance(recorded_raw, str):
            try:
                recorded_at = datetime.fromisoformat(recorded_raw)
            except ValueError:
                recorded_at = datetime.utcnow()
        else:
            recorded_at = datetime.utcnow()
        return GameplanExecution(actual=actual, comparison=comparison, recorded_at=recorded_at)
@dataclass(frozen=True)
class OpponentScoutingReport:
    """Lightweight opponent summary shown alongside the gameplan."""

    opponent: TeamInfo
    record: str
    offense_rank: int
    defense_rank: int
    explosive_rate: float
    pressure_rate_allowed: float
    last_five_results: List[str]
    key_players: List[str]
    narrative: str


class GameplanRepository:
    """Persistence and helper logic for weekly gameplans."""

    def __init__(self, user_home: Path, *, team_repository: Optional[TeamRepository] = None) -> None:
        self._user_home = user_home
        settings_dir = user_home / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self._plans_path = settings_dir / "gameplans.json"
        self._team_repo = team_repository or TeamRepository()
        self._plans: Dict[str, Dict[str, object]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_plan(self, team_id: str, opponent_id: Optional[str] = None, week: int | None = None) -> WeeklyGameplan:
        opponent_id = opponent_id or self._default_opponent(team_id, week or 1)
        week = week or 1
        key = self._plan_key(team_id, opponent_id, week)
        payload = self._plans.get(key)
        if payload:
            plan = WeeklyGameplan.from_dict(payload)
        else:
            plan = self._generate_default_plan(team_id, opponent_id, week)
            self.save_plan(plan)
        return plan

    def save_plan(self, plan: WeeklyGameplan) -> WeeklyGameplan:
        plan.last_modified = datetime.utcnow()
        key = self._plan_key(plan.team_id, plan.opponent_id, plan.week)
        self._plans[key] = plan.to_dict()
        self._persist()
        return plan

    def delete_plan(self, team_id: str, opponent_id: str, week: int) -> None:
        key = self._plan_key(team_id, opponent_id, week)
        if key in self._plans:
            self._plans.pop(key)
            self._persist()


    def record_execution(
        self,
        team_id: str,
        opponent_id: str,
        week: int,
        actual: Dict[str, float],
    ) -> GameplanExecution:
        plan = self.load_plan(team_id, opponent_id=opponent_id, week=week)
        comparison = self.compare_to_actual(plan, actual)
        execution = GameplanExecution(actual=actual, comparison=comparison, recorded_at=datetime.utcnow())
        key = self._plan_key(team_id, opponent_id, week)
        entry = self._plans.setdefault(key, plan.to_dict())
        entry["last_execution"] = execution.to_dict()
        self._plans[key] = entry
        self._persist()
        plan.last_execution = execution
        return execution


    def list_saved_plans(self, team_id: str) -> List[WeeklyGameplan]:
        plans: List[WeeklyGameplan] = []
        for payload in self._plans.values():
            if payload.get("team_id") == team_id:
                plans.append(WeeklyGameplan.from_dict(payload))
        plans.sort(key=lambda plan: (plan.week, plan.opponent_id))
        return plans

    def export_plan(self, plan: WeeklyGameplan, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = plan.to_dict()
        destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return destination

    def import_plan(self, source: Path, *, override_ids: Optional[tuple[str, str, int]] = None) -> WeeklyGameplan:
        payload = json.loads(source.read_text(encoding="utf-8"))
        plan = WeeklyGameplan.from_dict(payload)
        if override_ids is not None:
            team_id, opponent_id, week = override_ids
            plan.team_id = team_id
            plan.opponent_id = opponent_id
            plan.week = week
        self.save_plan(plan)
        return plan

    def preview(self, plan: WeeklyGameplan, *, drives: int = 10) -> GameplanPreview:
        plan.tendencies.clamp()
        total_plays = max(1, drives * 6)
        expected_run = round(total_plays * plan.tendencies.run_rate / 100)
        expected_pass = total_plays - expected_run
        deep_shots = round(expected_pass * plan.tendencies.deep_shot_rate / 100)
        blitz_calls = round(total_plays * plan.tendencies.blitz_rate / 100)
        zone_calls = round(total_plays * plan.tendencies.zone_rate / 100)
        explosive = min(0.65, 0.15 + plan.tendencies.deep_shot_rate / 250)
        takeaway = min(0.45, 0.10 + plan.tendencies.blitz_rate / 300)
        expected_points = round(total_plays * (0.28 + plan.tendencies.run_rate / 400), 1)
        return GameplanPreview(
            drives=drives,
            expected_run_calls=expected_run,
            expected_pass_calls=expected_pass,
            expected_deep_shots=deep_shots,
            expected_blitz_calls=blitz_calls,
            expected_zone_calls=zone_calls,
            explosive_play_chance=round(explosive, 3),
            takeaway_chance=round(takeaway, 3),
            expected_points=expected_points,
        )

    def compare_to_actual(self, plan: WeeklyGameplan, actual: Dict[str, float]) -> GameplanComparison:
        tend = plan.tendencies
        run_delta = (actual.get("run_rate", tend.run_rate) - tend.run_rate)
        deep_delta = (actual.get("deep_shot_rate", tend.deep_shot_rate) - tend.deep_shot_rate)
        blitz_delta = (actual.get("blitz_rate", tend.blitz_rate) - tend.blitz_rate)
        zone_delta = (actual.get("zone_rate", tend.zone_rate) - tend.zone_rate)
        return GameplanComparison(
            run_delta=run_delta,
            deep_delta=deep_delta,
            blitz_delta=blitz_delta,
            zone_delta=zone_delta,
        )

    def scouting_report(self, team_id: str, opponent_id: Optional[str] = None, week: int | None = None) -> OpponentScoutingReport:
        opponent_id = opponent_id or self._default_opponent(team_id, week or 1)
        opponent = self._team_repo.find_team(opponent_id) or TeamInfo(opponent_id, opponent_id, opponent_id, opponent_id)
        seed = f"scout-{team_id}-{opponent_id}-{week or 1}"
        rng = _DeterministicRandom(seed)
        record = f"{rng.randrange(6, 13)}-{rng.randrange(4, 11)}"
        offense_rank = rng.randrange(1, 33)
        defense_rank = rng.randrange(1, 33)
        explosive = round(0.18 + (32 - offense_rank) * 0.004, 3)
        pressure_allowed = round(0.24 + defense_rank * 0.003, 3)
        last_five: List[str] = []
        for _ in range(5):
            result = rng.choice(["W", "L"])
            margin = rng.randrange(1, 21)
            last_five.append(f"{result} by {margin}")
        key_players = [
            f"{opponent.abbreviation} Skill #{rng.randrange(80, 99)}",
            f"{opponent.abbreviation} Edge #{rng.randrange(80, 99)}",
        ]
        narrative = "Control early downs and force 3rd & 7+; blitz selectively to rattle their QB."
        return OpponentScoutingReport(
            opponent=opponent,
            record=record,
            offense_rank=offense_rank,
            defense_rank=defense_rank,
            explosive_rate=explosive,
            pressure_rate_allowed=pressure_allowed,
            last_five_results=last_five,
            key_players=key_players,
            narrative=narrative,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._plans_path.exists():
            self._plans = {}
            return
        try:
            payload = json.loads(self._plans_path.read_text(encoding="utf-8"))
            plans = payload.get("plans") if isinstance(payload, dict) else None
            if isinstance(plans, dict):
                self._plans = plans
            else:
                self._plans = {}
        except (json.JSONDecodeError, OSError):  # pragma: no cover - defensive
            self._plans = {}

    def _persist(self) -> None:
        data = {"plans": self._plans, "version": 1}
        self._plans_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _plan_key(self, team_id: str, opponent_id: str, week: int) -> str:
        return f"{team_id}:{opponent_id}:{week}"

    def _default_opponent(self, team_id: str, week: int) -> str:
        teams = self._team_repo.list_teams()
        if not teams:
            return "OPP"
        indices = {team.team_id: idx for idx, team in enumerate(teams)}
        index = indices.get(team_id, 0)
        opponent = teams[(index + week) % len(teams)]
        if opponent.team_id == team_id:
            opponent = teams[(index + 1) % len(teams)]
        return opponent.team_id

    def _generate_default_plan(self, team_id: str, opponent_id: str, week: int) -> WeeklyGameplan:
        seed = f"plan-{team_id}-{opponent_id}-{week}"
        rng = _DeterministicRandom(seed)
        tendencies = GameplanTendencies(
            run_rate=rng.randrange(45, 61),
            deep_shot_rate=rng.randrange(28, 46),
            blitz_rate=rng.randrange(18, 34),
            zone_rate=rng.randrange(50, 71),
        )
        situations = [
            SituationTendency(
                bucket=base[0],
                primary_call=base[1],
                secondary_call=base[2],
                notes="Exploit linebackers" if "3rd" in base[0] else "",
            )
            for base in _DEFAULT_SITUATIONS
        ]
        notes = "Blend of balanced run-pass with selective pressure."
        return WeeklyGameplan(
            team_id=team_id,
            opponent_id=opponent_id,
            week=week,
            tendencies=tendencies,
            situations=situations,
            notes=notes,
        )


class _DeterministicRandom:
    """Helper around Python's random for deterministic but lightweight values."""

    def __init__(self, seed: str) -> None:
        self._seed = seed

    def _value(self, extra: str) -> int:
        return abs(hash(f"{self._seed}:{extra}"))

    def randrange(self, start: int, stop: int) -> int:
        rng = self._value(str(start ^ stop))
        span = max(stop - start, 1)
        return start + (rng % span)

    def choice(self, options: Iterable[str]) -> str:
        options = list(options)
        if not options:
            return ""
        rng = self._value("choice")
        return options[rng % len(options)]


__all__ = [
    "GameplanRepository",
    "WeeklyGameplan",
    "GameplanTendencies",
    "SituationTendency",
    "GameplanPreview",
    "GameplanComparison",
    "GameplanExecution",
    "OpponentScoutingReport",
]
