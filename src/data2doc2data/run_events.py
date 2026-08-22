"""Observable, bounded run-event contracts for workbench replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .workspace import CONTRACT_VERSION, WorkspaceContractError, _require_identifier, _require_timestamp, _utc_now


MAX_SUMMARY_BYTES = 4096
EVENT_KINDS = frozenset(
    {
        "run.started",
        "run.completed",
        "run.failed",
        "step.started",
        "step.completed",
        "step.failed",
        "data.profiled",
        "compute.plan.created",
        "compute.result.created",
        "chart.spec.created",
        "chart.rendered",
        "document.indexed",
        "retrieval.result.created",
        "claim.extracted",
        "hypothesis.created",
        "validation.completed",
        "evidence.linked",
        "conclusion.created",
        "approval.requested",
        "approval.decided",
    }
)
_FORBIDDEN_SUMMARY_KEYS = frozenset({"raw", "raw_data", "raw_rows", "records", "rows_data", "chain_of_thought"})


class RunEventError(ValueError):
    """Raised when an observable event violates its safe public contract."""


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _FORBIDDEN_SUMMARY_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_summary(summary: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(summary, Mapping):
        raise RunEventError("summary must be an object")
    copied = dict(summary)
    if _contains_forbidden_key(copied):
        raise RunEventError("raw data is not allowed in event summaries")
    try:
        encoded = json.dumps(copied, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RunEventError("summary must be JSON serializable") from exc
    if len(encoded) > MAX_SUMMARY_BYTES:
        raise RunEventError("summary must remain bounded")
    return _freeze_json(json.loads(encoded.decode("utf-8")))


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    sequence: int
    kind: str
    phase: str
    summary: Mapping[str, Any]
    artifact_refs: tuple[str, ...]
    created_at: str
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise RunEventError(f"unsupported contract_version: {self.contract_version!r}")
        try:
            _require_identifier(self.run_id, "run_id")
            _require_identifier(self.phase, "phase")
            for artifact_ref in self.artifact_refs:
                _require_identifier(artifact_ref, "artifact_ref")
            _require_timestamp(self.created_at, "created_at")
        except WorkspaceContractError as exc:
            raise RunEventError(str(exc)) from exc
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise RunEventError("sequence must be a positive integer")
        if self.kind not in EVENT_KINDS:
            raise RunEventError(f"unknown event kind: {self.kind!r}")
        object.__setattr__(self, "summary", _validate_summary(self.summary))
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))

    @classmethod
    def create(
        cls,
        run_id: str,
        sequence: int,
        kind: str,
        phase: str,
        summary: Mapping[str, Any],
        artifact_refs: Iterable[str] = (),
        now: str | None = None,
    ) -> RunEvent:
        return cls(run_id, sequence, kind, phase, dict(summary), tuple(artifact_refs), now or _utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "kind": self.kind,
            "phase": self.phase,
            "summary": _thaw_json(self.summary),
            "artifact_refs": list(self.artifact_refs),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RunEvent:
        summary = payload.get("summary", {})
        refs = payload.get("artifact_refs", ())
        if not isinstance(summary, Mapping):
            raise RunEventError("summary must be an object")
        if not isinstance(refs, (list, tuple)):
            raise RunEventError("artifact_refs must be a list")
        return cls(
            run_id=str(payload.get("run_id", "")),
            sequence=payload.get("sequence"),
            kind=str(payload.get("kind", "")),
            phase=str(payload.get("phase", "")),
            summary=dict(summary),
            artifact_refs=tuple(str(ref) for ref in refs),
            created_at=str(payload.get("created_at", "")),
            contract_version=payload.get("contract_version"),
        )


def validate_event_stream(events: Iterable[RunEvent]) -> tuple[RunEvent, ...]:
    ordered = tuple(events)
    if not ordered:
        return ordered
    run_id = ordered[0].run_id
    expected = ordered[0].sequence
    for event in ordered:
        if event.run_id != run_id:
            raise RunEventError("all events must belong to the same run")
        if event.sequence != expected:
            raise RunEventError("event sequences must be contiguous and monotonic")
        expected += 1
    return ordered
