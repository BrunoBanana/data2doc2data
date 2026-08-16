"""Compact, server-owned evidence context for local agent conversations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .analysis import MAX_DOCUMENT_BYTES, read_metrics_source, resolve_sources
from .config import Profile
from .demo_scenarios import DemoScenarioCatalog
from .metrics import InputValidationError


@dataclass(frozen=True)
class SourceProfile:
    fingerprint: str
    mode: str
    label: str
    synthetic: bool
    record_count: int
    metrics: tuple[str, ...]
    observation_dates: tuple[str, ...]
    document_count: int
    source_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_source_profile(profile: Profile) -> SourceProfile:
    csv_path, document_paths = resolve_sources(profile)
    rows, csv_digest = read_metrics_source(csv_path)
    document_digests = tuple(_document_digest(path) for path in document_paths)
    source_hashes = (csv_digest, *document_digests)
    identity = {
        "mode": profile.mode,
        "paths": [str(csv_path.resolve()), *(str(path.resolve()) for path in document_paths)],
        "hashes": source_hashes,
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if profile.mode == "demo":
        label = DemoScenarioCatalog.load().get(profile.demo_scenario).label
    else:
        label = csv_path.name
    return SourceProfile(
        fingerprint=fingerprint,
        mode=profile.mode,
        label=label,
        synthetic=profile.mode == "demo",
        record_count=len(rows),
        metrics=tuple(sorted({row.metric for row in rows})),
        observation_dates=tuple(sorted({row.date.isoformat() for row in rows})),
        document_count=len(document_paths),
        source_hashes=source_hashes,
    )


def _document_digest(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise InputValidationError(f"document is too large: {path.name}")
        content = path.read_bytes()
    except OSError as error:
        raise InputValidationError(f"cannot read document: {error}") from error
    if len(content) > MAX_DOCUMENT_BYTES:
        raise InputValidationError(f"document is too large: {path.name}")
    return hashlib.sha256(content).hexdigest()
