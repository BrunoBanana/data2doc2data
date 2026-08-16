"""Content-derived provenance records for reproducible local analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json


ENGINE_VERSION = "2.9.0"


@dataclass(frozen=True)
class SourceRef:
    path: str
    sha256: str
    rows: tuple[int, ...] = ()
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class AnalysisProvenance:
    analysis_id: str
    engine_version: str
    sources: tuple[SourceRef, ...]
    parameters: dict[str, object]


def build_provenance(
    sources: tuple[SourceRef, ...],
    parameters: dict[str, object],
    engine_version: str = ENGINE_VERSION,
) -> AnalysisProvenance:
    canonical_parameters = json.loads(
        json.dumps(parameters, ensure_ascii=False, sort_keys=True, allow_nan=False)
    )
    ordered_sources = tuple(
        sorted(
            sources,
            key=lambda source: (
                source.path,
                source.rows,
                source.start_line or 0,
                source.end_line or 0,
            ),
        )
    )
    canonical = json.dumps(
        {
            "engine_version": engine_version,
            "sources": [asdict(source) for source in ordered_sources],
            "parameters": canonical_parameters,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    analysis_id = hashlib.sha256(canonical).hexdigest()
    return AnalysisProvenance(analysis_id, engine_version, ordered_sources, canonical_parameters)
