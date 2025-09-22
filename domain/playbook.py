from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Sequence

from pydantic import ValidationError

from domain.models import Play

LOGGER = logging.getLogger("domain.playbook")

DEFAULT_METADATA_FILE = "playbooks.json"
DEFAULT_USAGE_FILE = "play_usage.json"


class PlaybookError(Exception):
    """Base exception for playbook repository failures."""


class PlayAlreadyExistsError(PlaybookError):
    """Raised when attempting to save a play that already exists without overwrite."""


class PlayValidationError(PlaybookError):
    """Raised when a play fails structural or business validation."""

    def __init__(self, errors: List[Dict[str, object]]) -> None:
        super().__init__("Play failed validation")
        self.errors = errors


@dataclass
class PlayMetadata:
    play_id: str
    tags: List[str] = field(default_factory=list)
    version: int = 1
    last_modified: datetime | None = None

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "tags": sorted(set(self.tags)),
            "version": int(self.version),
        }
        if self.last_modified is not None:
            payload["last_modified"] = self.last_modified.isoformat()
        return payload

    @staticmethod
    def from_dict(play_id: str, payload: Dict[str, object]) -> "PlayMetadata":
        raw_tags = payload.get("tags")
        tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
        version = int(payload.get("version", 1))
        raw_timestamp = payload.get("last_modified")
        last_modified: datetime | None = None
        if isinstance(raw_timestamp, str):
            try:
                last_modified = datetime.fromisoformat(raw_timestamp)
            except ValueError:
                last_modified = None
        return PlayMetadata(
            play_id=play_id,
            tags=tags,
            version=version,
            last_modified=last_modified,
        )


@dataclass(frozen=True)
class PlayUsage:
    play_id: str
    calls: int = 0
    success_rate: float = 0.0
    avg_gain: float = 0.0
    last_used: datetime | None = None


@dataclass(frozen=True)
class PlaySummary:
    play_id: str
    name: str
    formation: str
    personnel: str
    play_type: str
    tags: List[str]
    version: int
    usage: PlayUsage
    path: Path
    last_modified: datetime | None


@dataclass(frozen=True)
class PlayFilters:
    formation: Optional[str] = None
    personnel: Optional[str] = None
    tag: Optional[str] = None
    search: Optional[str] = None


def _role_requires_route(role: str) -> bool:
    return role in {"route", "defend", "rush"}


def _sanitize_error_context(errors: List[Dict[str, object]]) -> List[Dict[str, object]]:
    sanitized: List[Dict[str, object]] = []
    for error in errors:
        ctx = error.get("ctx")
        if isinstance(ctx, dict):
            error = {**error, "ctx": {key: str(value) for key, value in ctx.items()}}
        sanitized.append(error)
    return sanitized


def validate_play(play: Play) -> List[Dict[str, object]]:
    errors: List[Dict[str, object]] = []
    seen_players: set[str] = set()

    for index, assignment in enumerate(play.assignments):
        if assignment.player_id in seen_players:
            errors.append(
                {
                    "loc": ["assignments", index, "player_id"],
                    "msg": f"duplicate assignment for player '{assignment.player_id}'",
                    "type": "value_error.duplicate",
                }
            )
        else:
            seen_players.add(assignment.player_id)

        if _role_requires_route(assignment.role) and not assignment.route:
            errors.append(
                {
                    "loc": ["assignments", index, "route"],
                    "msg": f"role '{assignment.role}' requires a route",
                    "type": "value_error.route_required",
                }
            )

    role_counts = Counter(assignment.role for assignment in play.assignments)

    if play.play_type == "offense":
        if role_counts.get("pass", 0) > 1:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "offense play can have at most one 'pass' assignment",
                    "type": "value_error.role_count",
                }
            )
        if role_counts.get("pass", 0) + role_counts.get("carry", 0) == 0:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "offense play requires at least one 'pass' or 'carry' assignment",
                    "type": "value_error.role_required",
                }
            )
    elif play.play_type == "special_teams":
        if role_counts.get("kick", 0) != 1:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "special_teams play requires exactly one 'kick' assignment",
                    "type": "value_error.role_required",
                }
            )
    elif play.play_type == "defense":
        if role_counts.get("defend", 0) + role_counts.get("rush", 0) == 0:
            errors.append(
                {
                    "loc": ["assignments"],
                    "msg": "defense play requires at least one 'defend' or 'rush' assignment",
                    "type": "value_error.role_required",
                }
            )

    return errors


class PlayUsageProvider:
    """Abstract source for per-play usage statistics."""

    def stats_for(self, play_ids: Sequence[str]) -> Dict[str, PlayUsage]:  # pragma: no cover - interface
        raise NotImplementedError


class FilePlayUsageProvider(PlayUsageProvider):
    """Loads play usage metrics from a JSON file, with deterministic fallbacks."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def stats_for(self, play_ids: Sequence[str]) -> Dict[str, PlayUsage]:
        data = self._load_data()
        stats: Dict[str, PlayUsage] = {}
        for play_id in play_ids:
            payload = data.get(play_id)
            if isinstance(payload, dict):
                last_used: datetime | None = None
                raw_last_used = payload.get("last_used")
                if isinstance(raw_last_used, str):
                    try:
                        last_used = datetime.fromisoformat(raw_last_used)
                    except ValueError:
                        last_used = None
                stats[play_id] = PlayUsage(
                    play_id=play_id,
                    calls=int(payload.get("calls", 0)),
                    success_rate=float(payload.get("success_rate", 0.0)),
                    avg_gain=float(payload.get("avg_gain", 0.0)),
                    last_used=last_used,
                )
            else:
                stats[play_id] = self._fallback_usage(play_id)
        return stats

    def _load_data(self) -> Dict[str, Dict[str, object]]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):  # pragma: no cover - defensive
            return {}
        if isinstance(raw, dict):
            return {
                str(key): value
                for key, value in raw.items()
                if isinstance(value, dict)
            }
        return {}

    def _fallback_usage(self, play_id: str) -> PlayUsage:
        seed = abs(hash(play_id))
        calls = 6 + seed % 24
        success_rate = 0.35 + (seed % 30) / 100.0
        avg_gain = 3.0 + (seed % 40) * 0.1
        return PlayUsage(
            play_id=play_id,
            calls=calls,
            success_rate=round(min(success_rate, 0.8), 3),
            avg_gain=round(avg_gain, 2),
            last_used=None,
        )


class PlaybookRepository:
    """Manages play files, metadata, and usage stats for the UI and API."""

    def __init__(
        self,
        plays_dir: Path | None = None,
        user_home: Path | None = None,
        *,
        usage_provider: PlayUsageProvider | None = None,
    ) -> None:
        self._plays_dir = (plays_dir or Path("data/plays")).resolve()
        self._plays_dir.mkdir(parents=True, exist_ok=True)
        base = (user_home or Path("data/state")).resolve()
        base.mkdir(parents=True, exist_ok=True)
        self._meta_path = base / DEFAULT_METADATA_FILE
        if usage_provider is None:
            usage_path = base / DEFAULT_USAGE_FILE
            self._usage_provider = FilePlayUsageProvider(usage_path)
        else:
            self._usage_provider = usage_provider
        self._metadata: Dict[str, PlayMetadata] = self._load_metadata()

    # ------------------------------------------------------------------
    # Metadata helpers
    # ------------------------------------------------------------------
    def _load_metadata(self) -> Dict[str, PlayMetadata]:
        if not self._meta_path.exists():
            return {}
        try:
            raw = json.loads(self._meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to parse playbook metadata: %s", exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        metadata: Dict[str, PlayMetadata] = {}
        for play_id, payload in raw.items():
            if isinstance(payload, dict):
                metadata[str(play_id)] = PlayMetadata.from_dict(str(play_id), payload)
        return metadata

    def _persist_metadata(self) -> None:
        data = {
            play_id: meta.to_dict()
            for play_id, meta in sorted(self._metadata.items())
        }
        try:
            self._meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            LOGGER.warning("Unable to persist playbook metadata: %s", exc)

    def _metadata_for(self, play_id: str, *, ensure: bool = False) -> PlayMetadata:
        meta = self._metadata.get(play_id)
        if meta is None and ensure:
            meta = PlayMetadata(play_id=play_id)
            path = self._plays_dir / f"{play_id}.json"
            try:
                stat = path.stat()
                meta.last_modified = datetime.fromtimestamp(stat.st_mtime)
            except OSError:
                meta.last_modified = None
            self._metadata[play_id] = meta
        return meta  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Listing and filters
    # ------------------------------------------------------------------
    def list_plays(
        self,
        play_type: Literal["offense", "defense", "special_teams"] | None = None,
        *,
        filters: PlayFilters | None = None,
    ) -> List[PlaySummary]:
        records: List[tuple[Play, Path, PlayMetadata]] = []
        for path in sorted(self._plays_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                LOGGER.warning("Unable to read play file %s: %s", path, exc)
                continue
            try:
                play = Play.model_validate(payload)
            except ValidationError as exc:
                LOGGER.warning("Skipping invalid play file %s: %s", path, exc)
                continue
            errors = validate_play(play)
            if errors:
                LOGGER.warning("Skipping play %s due to validation errors", play.play_id)
                continue
            if play_type and play.play_type != play_type:
                continue
            meta = self._metadata_for(play.play_id, ensure=True)
            if filters and not self._match_filters(play, meta, filters):
                continue
            records.append((play, path, meta))

        play_ids = [play.play_id for play, _, _ in records]
        usage_map = self._usage_provider.stats_for(play_ids) if play_ids else {}
        summaries: List[PlaySummary] = []
        for play, path, meta in records:
            if meta.last_modified is None:
                try:
                    meta.last_modified = datetime.fromtimestamp(path.stat().st_mtime)
                except OSError:
                    meta.last_modified = None
            usage = usage_map.get(play.play_id, PlayUsage(play.play_id))
            summaries.append(
                PlaySummary(
                    play_id=play.play_id,
                    name=play.name,
                    formation=play.formation,
                    personnel=play.personnel,
                    play_type=play.play_type,
                    tags=sorted(set(meta.tags)),
                    version=meta.version,
                    usage=usage,
                    path=path,
                    last_modified=meta.last_modified,
                )
            )
        summaries.sort(key=lambda item: (item.play_type, item.name.lower()))
        return summaries

    def _match_filters(self, play: Play, meta: PlayMetadata, filters: PlayFilters) -> bool:
        if filters.formation and play.formation != filters.formation:
            return False
        if filters.personnel and play.personnel != filters.personnel:
            return False
        if filters.tag and filters.tag not in meta.tags:
            return False
        if filters.search:
            needle = filters.search.lower()
            haystack = " ".join(
                [
                    play.name,
                    play.formation,
                    play.personnel,
                    play.play_id,
                    " ".join(meta.tags),
                ]
            ).lower()
            if needle not in haystack:
                return False
        return True

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    def load_play(self, play_id: str) -> tuple[Play, Path]:
        path = self._plays_dir / f"{play_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Play '{play_id}' does not exist")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PlaybookError(f"Unable to read play '{play_id}': {exc}") from exc
        try:
            play = Play.model_validate(payload)
        except ValidationError as exc:
            raise PlayValidationError(_sanitize_error_context(exc.errors())) from exc
        errors = validate_play(play)
        if errors:
            raise PlayValidationError(errors)
        return play, path

    def save_play(self, play: Play, *, overwrite: bool = False) -> Path:
        errors = validate_play(play)
        if errors:
            raise PlayValidationError(errors)
        path = self._plays_dir / f"{play.play_id}.json"
        if path.exists() and not overwrite:
            raise PlayAlreadyExistsError(f"Play '{play.play_id}' already exists")
        metadata = self._metadata_for(play.play_id, ensure=True)
        if path.exists():
            metadata.version += 1
        else:
            metadata.version = max(metadata.version, 1)
        metadata.last_modified = datetime.utcnow()
        payload = play.model_dump(mode="json")
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            raise PlaybookError(f"Unable to write play '{play.play_id}': {exc}") from exc
        self._metadata[play.play_id] = metadata
        self._persist_metadata()
        return path

    def import_play_file(self, source: Path, *, overwrite: bool = False) -> Play:
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PlaybookError(f"Unable to read play file '{source}': {exc}") from exc
        try:
            play = Play.model_validate(payload)
        except ValidationError as exc:
            raise PlayValidationError(_sanitize_error_context(exc.errors())) from exc
        self.save_play(play, overwrite=overwrite)
        return play

    def export_play(self, play_id: str, destination: Path) -> Path:
        play, _ = self.load_play(play_id)
        dest = destination
        if dest.exists() and dest.is_dir():
            dest = dest / f"{play_id}.json"
        elif dest.suffix.lower() != ".json":
            dest = dest.with_suffix(".json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = play.model_dump(mode="json")
        dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return dest

    def mirror_play(
        self,
        play_id: str,
        *,
        new_play_id: Optional[str] = None,
        new_name: Optional[str] = None,
    ) -> Play:
        play, _ = self.load_play(play_id)
        payload = play.model_dump(mode="python", round_trip=True)
        mirrored_id = new_play_id or f"{play.play_id}_flip"
        candidate = mirrored_id
        suffix = 2
        while (self._plays_dir / f"{candidate}.json").exists():
            candidate = f"{mirrored_id}_{suffix}"
            suffix += 1
        mirrored_id = candidate
        payload["play_id"] = mirrored_id
        payload["name"] = new_name or f"{play.name} (Flip)"
        for assignment in payload.get("assignments", []):
            route = assignment.get("route")
            if isinstance(route, list):
                for point in route:
                    if isinstance(point, dict) and "x" in point:
                        point["x"] = -float(point["x"])
        mirrored = Play.model_validate(payload)
        self.save_play(mirrored, overwrite=False)
        meta = self._metadata_for(mirrored.play_id, ensure=True)
        if "Mirrored" not in meta.tags:
            meta.tags.append("Mirrored")
            meta.tags = sorted(set(meta.tags))
        self._metadata[mirrored.play_id] = meta
        self._persist_metadata()
        return mirrored

    def update_tags(self, play_id: str, tags: Iterable[str]) -> PlayMetadata:
        metadata = self._metadata_for(play_id, ensure=True)
        cleaned = sorted({tag.strip() for tag in tags if tag.strip()})
        metadata.tags = cleaned
        metadata.last_modified = datetime.utcnow()
        self._metadata[play_id] = metadata
        self._persist_metadata()
        return metadata

    def bump_version(self, play_id: str) -> PlayMetadata:
        metadata = self._metadata_for(play_id, ensure=True)
        metadata.version += 1
        metadata.last_modified = datetime.utcnow()
        self._metadata[play_id] = metadata
        self._persist_metadata()
        return metadata

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------
    def available_tags(self) -> List[str]:
        tags: set[str] = set()
        for meta in self._metadata.values():
            tags.update(meta.tags)
        return sorted(tags)

    def available_formations(self) -> List[str]:
        formations: set[str] = set()
        for summary in self.list_plays():
            formations.add(summary.formation)
        return sorted(formations)

    def available_personnel(self) -> List[str]:
        personnel: set[str] = set()
        for summary in self.list_plays():
            personnel.add(summary.personnel)
        return sorted(personnel)


__all__ = [
    "PlaybookRepository",
    "PlayFilters",
    "PlaySummary",
    "PlayMetadata",
    "PlayUsage",
    "PlayUsageProvider",
    "FilePlayUsageProvider",
    "PlaybookError",
    "PlayAlreadyExistsError",
    "PlayValidationError",
    "validate_play",
]
