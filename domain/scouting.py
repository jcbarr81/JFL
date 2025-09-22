from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from domain.roster import RosterPlayer, RosterRepository
from domain.teams import TeamInfo, TeamRepository
from domain.db import PositionEnum


@dataclass(frozen=True)
class CombineMetrics:
    forty_time: float
    shuttle: float
    three_cone: float
    bench_reps: int
    vertical: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "forty_time": self.forty_time,
            "shuttle": self.shuttle,
            "three_cone": self.three_cone,
            "bench_reps": self.bench_reps,
            "vertical": self.vertical,
        }


@dataclass(frozen=True)
class ProspectProfile:
    prospect_id: str
    name: str
    position: str
    college: str
    archetype: str
    true_grade: float
    combine: CombineMetrics
    projected_round: int

    def to_dict(self) -> Dict[str, object]:
        payload = {
            "prospect_id": self.prospect_id,
            "name": self.name,
            "position": self.position,
            "college": self.college,
            "archetype": self.archetype,
            "true_grade": self.true_grade,
            "projected_round": self.projected_round,
        }
        payload["combine"] = self.combine.to_dict()
        return payload


@dataclass(frozen=True)
class ProspectReport:
    prospect_id: str
    name: str
    position: str
    college: str
    archetype: str
    grade: float
    projected_round: int
    combine_summary: str
    watchlisted: bool
    drafted: bool


@dataclass(frozen=True)
class DraftPickRecord:
    pick_number: int
    round_number: int
    selection_index: int
    team_id: str
    team_name: str
    prospect_id: str
    prospect_name: str
    position: str
    grade: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "pick_number": self.pick_number,
            "round_number": self.round_number,
            "selection_index": self.selection_index,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "prospect_id": self.prospect_id,
            "prospect_name": self.prospect_name,
            "position": self.position,
            "grade": self.grade,
        }


@dataclass(frozen=True)
class DraftPickResult:
    record: DraftPickRecord
    roster_player: RosterPlayer
    roster_size: int


class ScoutingRepository:
    """Loads prospects, manages scouting noise, and tracks draft board state."""

    _TIER_NAMES = ("T1", "T2", "T3", "T4", "T5")

    def __init__(self, user_home: Path) -> None:
        self._user_home = user_home
        settings_dir = user_home / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self._prospects_path = settings_dir / "prospects.json"
        self._state_path = settings_dir / "scouting.json"
        self._exports_dir = user_home / "exports"
        self._roster_repo = RosterRepository(user_home)
        self._team_repo = TeamRepository()
        self._random = random.Random(20240921)
        self._prospects: Dict[str, ProspectProfile] = {}
        self._state = {
            "budget": 55,
            "watchlist": [],
            "tiers": {tier: [] for tier in self._TIER_NAMES},
            "drafted": [],
        }
        self._load_prospects()
        self._load_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def list_prospects(
        self,
        *,
        position: Optional[str] = None,
        watchlist_only: bool = False,
    ) -> List[ProspectReport]:
        watchlist = set(self._state.get("watchlist", []))
        drafted = {entry["prospect_id"] for entry in self._state.get("drafted", [])}
        reports: List[ProspectReport] = []
        for prospect in sorted(
            self._prospects.values(),
            key=lambda item: item.true_grade,
            reverse=True,
        ):
            if position and prospect.position != position:
                continue
            is_watchlisted = prospect.prospect_id in watchlist
            if watchlist_only and not is_watchlisted:
                continue
            grade = self._scouted_grade(prospect)
            combine_summary = self._combine_summary(prospect)
            reports.append(
                ProspectReport(
                    prospect_id=prospect.prospect_id,
                    name=prospect.name,
                    position=prospect.position,
                    college=prospect.college,
                    archetype=prospect.archetype,
                    grade=grade,
                    projected_round=prospect.projected_round,
                    combine_summary=combine_summary,
                    watchlisted=is_watchlisted,
                    drafted=prospect.prospect_id in drafted,
                )
            )
        return reports

    def get_prospect(self, prospect_id: str) -> Optional[ProspectProfile]:
        return self._prospects.get(prospect_id)

    def get_budget(self) -> int:
        return int(self._state.get("budget", 55))

    def set_budget(self, value: int) -> int:
        value = max(10, min(100, int(value)))
        self._state["budget"] = value
        self._write_state()
        return value

    def set_watchlist(self, prospect_id: str, enabled: bool) -> None:
        watchlist: List[str] = list(self._state.get("watchlist", []))
        if enabled and prospect_id not in watchlist:
            watchlist.append(prospect_id)
        elif not enabled and prospect_id in watchlist:
            watchlist.remove(prospect_id)
        self._state["watchlist"] = watchlist
        self._write_state()

    def toggle_watchlist(self, prospect_id: str) -> bool:
        watchlist = set(self._state.get("watchlist", []))
        enabled = prospect_id not in watchlist
        self.set_watchlist(prospect_id, enabled)
        return enabled

    def get_board(self) -> Dict[str, List[str]]:
        tiers = {tier: list(self._state.get("tiers", {}).get(tier, [])) for tier in self._TIER_NAMES}
        for tier, items in tiers.items():
            tiers[tier] = [pid for pid in items if pid in self._prospects]
        return tiers

    def assign_to_tier(self, prospect_id: str, tier: str, *, index: Optional[int] = None) -> None:
        if tier not in self._TIER_NAMES or prospect_id not in self._prospects:
            return
        tiers = self.get_board()
        for bucket in tiers.values():
            if prospect_id in bucket:
                bucket.remove(prospect_id)
        bucket = tiers[tier]
        if index is None or index < 0 or index > len(bucket):
            bucket.append(prospect_id)
        else:
            bucket.insert(index, prospect_id)
        self._state["tiers"] = tiers
        self._write_state()

    def remove_from_board(self, prospect_id: str) -> None:
        tiers = self.get_board()
        changed = False
        for bucket in tiers.values():
            if prospect_id in bucket:
                bucket.remove(prospect_id)
                changed = True
        if changed:
            self._state["tiers"] = tiers
            self._write_state()

    def list_draft_recap(self) -> List[DraftPickRecord]:
        recap = []
        for entry in self._state.get("drafted", []):
            recap.append(
                DraftPickRecord(
                    pick_number=int(entry.get("pick_number", 0)),
                    round_number=int(entry.get("round_number", 0)),
                    selection_index=int(entry.get("selection_index", 0)),
                    team_id=str(entry.get("team_id", "")),
                    team_name=str(entry.get("team_name", "")),
                    prospect_id=str(entry.get("prospect_id", "")),
                    prospect_name=str(entry.get("prospect_name", "")),
                    position=str(entry.get("position", "")),
                    grade=float(entry.get("grade", 0.0)),
                )
            )
        recap.sort(key=lambda item: (item.round_number, item.selection_index))
        return recap

    def record_draft_pick(
        self,
        team: TeamInfo,
        prospect_id: str,
        round_number: int,
        selection_index: int,
    ) -> Optional[DraftPickResult]:
        profile = self._prospects.get(prospect_id)
        if profile is None:
            return None
        drafted_ids = {entry["prospect_id"] for entry in self._state.get("drafted", [])}
        if prospect_id in drafted_ids:
            return None
        pick_number = (round_number - 1) * 32 + selection_index
        grade = self._scouted_grade(profile, reveal=True)
        roster_player = self._prospect_to_player(profile)
        roster = self._roster_repo.list_players(team.team_id)
        roster.append(roster_player)
        self._roster_repo.save_roster(team.team_id, roster)
        try:
            self._roster_repo.auto_fix(team.team_id)
        except Exception:
            pass
        record = DraftPickRecord(
            pick_number=pick_number,
            round_number=round_number,
            selection_index=selection_index,
            team_id=team.team_id,
            team_name=team.display_name,
            prospect_id=prospect_id,
            prospect_name=profile.name,
            position=profile.position,
            grade=grade,
        )
        drafted = list(self._state.get("drafted", []))
        drafted.append(record.to_dict())
        self._state["drafted"] = drafted
        self.remove_from_board(prospect_id)
        self._write_state()
        roster_size = len(roster)
        return DraftPickResult(record=record, roster_player=roster_player, roster_size=roster_size)

    def export_draft_class(self) -> Path:
        self._exports_dir.mkdir(parents=True, exist_ok=True)
        export_path = self._exports_dir / f"draft_class_{datetime.utcnow():%Y%m%d%H%M%S}.csv"
        with export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "Prospect ID",
                "Name",
                "Position",
                "College",
                "Archetype",
                "True Grade",
                "Projected Round",
                "40 Time",
                "Shuttle",
                "3-Cone",
                "Bench Reps",
                "Vertical",
            ])
            for prospect in sorted(self._prospects.values(), key=lambda p: p.true_grade, reverse=True):
                combine = prospect.combine
                writer.writerow([
                    prospect.prospect_id,
                    prospect.name,
                    prospect.position,
                    prospect.college,
                    prospect.archetype,
                    f"{prospect.true_grade:.1f}",
                    prospect.projected_round,
                    f"{combine.forty_time:.2f}",
                    f"{combine.shuttle:.2f}",
                    f"{combine.three_cone:.2f}",
                    combine.bench_reps,
                    f"{combine.vertical:.1f}",
                ])
        return export_path

    def export_draft_results(self) -> Path:
        self._exports_dir.mkdir(parents=True, exist_ok=True)
        export_path = self._exports_dir / f"draft_results_{datetime.utcnow():%Y%m%d%H%M%S}.csv"
        with export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "Pick",
                "Round",
                "Selection",
                "Team",
                "Prospect",
                "Position",
                "Grade",
            ])
            for record in self.list_draft_recap():
                writer.writerow([
                    record.pick_number,
                    record.round_number,
                    record.selection_index,
                    record.team_name,
                    record.prospect_name,
                    record.position,
                    f"{record.grade:.1f}",
                ])
        return export_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_prospects(self) -> None:
        if self._prospects_path.exists():
            data = json.loads(self._prospects_path.read_text(encoding="utf-8"))
            for item in data:
                combine_payload = item.get("combine", {})
                combine = CombineMetrics(
                    forty_time=float(combine_payload.get("forty_time", 4.6)),
                    shuttle=float(combine_payload.get("shuttle", 4.2)),
                    three_cone=float(combine_payload.get("three_cone", 6.9)),
                    bench_reps=int(combine_payload.get("bench_reps", 20)),
                    vertical=float(combine_payload.get("vertical", 32.0)),
                )
                profile = ProspectProfile(
                    prospect_id=str(item["prospect_id"]),
                    name=str(item["name"]),
                    position=str(item["position"]),
                    college=str(item.get("college", "")),
                    archetype=str(item.get("archetype", "")),
                    true_grade=float(item.get("true_grade", 70.0)),
                    combine=combine,
                    projected_round=int(item.get("projected_round", 3)),
                )
                self._prospects[profile.prospect_id] = profile
            return
        prospects = self._generate_prospects()
        self._prospects = {item.prospect_id: item for item in prospects}
        payload = [item.to_dict() for item in prospects]
        self._prospects_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if not self._state_path.exists():
            self._write_state()
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._write_state()
            return
        if not isinstance(data, dict):
            return
        budget = int(data.get("budget", 55))
        watchlist = [pid for pid in data.get("watchlist", []) if pid in self._prospects]
        tiers = data.get("tiers", {})
        sanitized = {tier: [pid for pid in tiers.get(tier, []) if pid in self._prospects] for tier in self._TIER_NAMES}
        drafted = [entry for entry in data.get("drafted", []) if isinstance(entry, dict)]
        self._state = {
            "budget": max(10, min(100, budget)),
            "watchlist": watchlist,
            "tiers": sanitized,
            "drafted": drafted,
        }

    def _write_state(self) -> None:
        try:
            self._state_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _generate_prospects(self) -> List[ProspectProfile]:
        colleges = [
            "Alabama",
            "Ohio State",
            "Georgia",
            "USC",
            "LSU",
            "Michigan",
            "Clemson",
            "Oregon",
        ]
        archetypes = {
            "QB": ["Pocket", "Dual-Threat"],
            "RB": ["Power", "Elusive"],
            "WR": ["Route Runner", "Deep Threat"],
            "TE": ["Move", "Inline"],
            "OL": ["Pass Pro", "Mauler"],
            "DL": ["Edge", "Interior"],
            "LB": ["Mike", "Coverage"],
            "CB": ["Press", "Zone"],
            "S": ["Box", "Centerfield"],
        }
        position_counts: List[Tuple[str, int]] = [
            ("QB", 6),
            ("RB", 12),
            ("WR", 18),
            ("TE", 8),
            ("OL", 20),
            ("DL", 16),
            ("LB", 14),
            ("CB", 14),
            ("S", 8),
        ]
        prospects: List[ProspectProfile] = []
        for position, count in position_counts:
            for index in range(1, count + 1):
                prospect_id = f"{position}{index:03d}"
                rng = random.Random(f"{prospect_id}-seed")
                name = f"{position} Prospect {index}"
                college = rng.choice(colleges)
                archetype = rng.choice(archetypes.get(position, ["Balanced"]))
                base_grade = rng.uniform(55.0, 88.0)
                projected_round = max(1, min(7, int(math.ceil((100 - base_grade) / 7.5))))
                combine = CombineMetrics(
                    forty_time=round(rng.uniform(4.35, 4.95), 2),
                    shuttle=round(rng.uniform(4.0, 4.4), 2),
                    three_cone=round(rng.uniform(6.7, 7.2), 2),
                    bench_reps=int(rng.uniform(15, 32)),
                    vertical=round(rng.uniform(32, 42), 1),
                )
                prospects.append(
                    ProspectProfile(
                        prospect_id=prospect_id,
                        name=name,
                        position=position,
                        college=college,
                        archetype=archetype,
                        true_grade=round(base_grade, 1),
                        combine=combine,
                        projected_round=projected_round,
                    )
                )
        return prospects

    def _scouted_grade(self, prospect: ProspectProfile, reveal: bool = False) -> float:
        budget = self.get_budget()
        if reveal:
            return prospect.true_grade
        noise_span = max(2.0, (100 - budget) * 0.35)
        rng = random.Random(f"grade-{prospect.prospect_id}-{budget}")
        noise = rng.uniform(-noise_span, noise_span)
        grade = prospect.true_grade + noise
        return round(max(40.0, min(99.0, grade)), 1)

    def _combine_summary(self, prospect: ProspectProfile) -> str:
        budget = self.get_budget()
        if budget < 25:
            return "Limited data"
        combine = prospect.combine
        digits = 2 if budget >= 70 else 1 if budget >= 45 else 0
        def fmt_time(value: float) -> str:
            return f"{value:.{digits}f}"
        blur = max(0.0, (45 - budget) * 0.01)
        rng = random.Random(f"combine-{prospect.prospect_id}-{budget}")
        forty = fmt_time(combine.forty_time + rng.uniform(-blur, blur))
        shuttle = fmt_time(combine.shuttle + rng.uniform(-blur, blur))
        three_cone = fmt_time(combine.three_cone + rng.uniform(-blur, blur))
        bench = combine.bench_reps + int(rng.uniform(-2, 3))
        vertical = combine.vertical + rng.uniform(-1.5, 1.5)
        vertical_digits = 1 if budget >= 60 else 0
        return (
            f"40: {forty}s | Shuttle: {shuttle}s | 3C: {three_cone}s | Bench: {bench} | "
            f"Vert: {vertical:.{vertical_digits}f}".rstrip("0").rstrip(".")
        )

    def _prospect_to_player(self, prospect: ProspectProfile) -> RosterPlayer:
        rng = random.Random(f"player-{prospect.prospect_id}")
        jersey = rng.randint(10, 99)
        overall = int(round(prospect.true_grade))
        position = PositionEnum(prospect.position)
        player_id = f"rookie_{prospect.prospect_id}"
        return RosterPlayer(
            player_id=player_id,
            name=prospect.name,
            position=position,
            jersey_number=jersey,
            overall=overall,
        )


__all__ = [
    "CombineMetrics",
    "ProspectProfile",
    "ProspectReport",
    "DraftPickRecord",
    "DraftPickResult",
    "ScoutingRepository",
]
