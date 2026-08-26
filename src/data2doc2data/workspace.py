"""Versioned task and run contracts for the local analysis workbench."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class WorkspaceContractError(ValueError):
    """Raised when a task or run violates the public contract."""


class TaskStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _require_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise WorkspaceContractError(f"{field} must be a stable identifier")
    return value


def _require_text(value: str, field: str, maximum: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkspaceContractError(f"{field} must not be empty")
    cleaned = value.strip()
    if len(cleaned) > maximum:
        raise WorkspaceContractError(f"{field} is too long")
    return cleaned


def _require_timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise WorkspaceContractError(f"{field} must be a UTC timestamp")
    try:
        _parse_utc_timestamp(value)
    except ValueError as exc:
        raise WorkspaceContractError(f"{field} must be a UTC timestamp") from exc
    return value


def _require_version(value: Any) -> int:
    if value != CONTRACT_VERSION:
        raise WorkspaceContractError(f"unsupported contract_version: {value!r}")
    return CONTRACT_VERSION


@dataclass(frozen=True)
class SnapshotRef:
    kind: str
    snapshot_id: str
    sha256: str

    def __post_init__(self) -> None:
        if self.kind not in {"dataset", "document"}:
            raise WorkspaceContractError("snapshot kind must be dataset or document")
        _require_identifier(self.snapshot_id, "snapshot_id")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise WorkspaceContractError("sha256 must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "snapshot_id": self.snapshot_id, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SnapshotRef:
        return cls(
            kind=str(payload.get("kind", "")),
            snapshot_id=str(payload.get("snapshot_id", "")),
            sha256=str(payload.get("sha256", "")),
        )


def _snapshot_refs(values: Iterable[SnapshotRef]) -> tuple[SnapshotRef, ...]:
    refs = tuple(values)
    if any(not isinstance(ref, SnapshotRef) for ref in refs):
        raise WorkspaceContractError("snapshot_refs must contain SnapshotRef values")
    identities = {(ref.kind, ref.snapshot_id) for ref in refs}
    if len(identities) != len(refs):
        raise WorkspaceContractError("snapshot_refs must be unique")
    return refs


@dataclass(frozen=True)
class AnalysisTask:
    task_id: str
    title: str
    goal: str
    status: TaskStatus
    snapshot_refs: tuple[SnapshotRef, ...]
    created_at: str
    updated_at: str
    analysis_mode: str = "demo"
    agent_provider: str | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_version(self.contract_version)
        _require_identifier(self.task_id, "task_id")
        object.__setattr__(self, "title", _require_text(self.title, "title", 200))
        object.__setattr__(self, "goal", _require_text(self.goal, "goal"))
        object.__setattr__(self, "status", TaskStatus(self.status))
        object.__setattr__(self, "snapshot_refs", _snapshot_refs(self.snapshot_refs))
        _require_timestamp(self.created_at, "created_at")
        _require_timestamp(self.updated_at, "updated_at")
        if self.analysis_mode not in {"demo", "connected"}:
            raise WorkspaceContractError("analysis_mode must be demo or connected")
        if self.analysis_mode == "connected":
            if self.agent_provider is None:
                raise WorkspaceContractError("connected analysis requires an agent_provider")
            _require_identifier(self.agent_provider, "agent_provider")
        elif self.agent_provider is not None:
            raise WorkspaceContractError("demo analysis cannot set an agent_provider")

    @classmethod
    def create(
        cls,
        task_id: str,
        title: str,
        goal: str,
        snapshot_refs: Iterable[SnapshotRef] = (),
        now: str | None = None,
        *,
        analysis_mode: str = "demo",
        agent_provider: str | None = None,
    ) -> AnalysisTask:
        timestamp = now or _utc_now()
        return cls(
            task_id,
            title,
            goal,
            TaskStatus.ACTIVE,
            tuple(snapshot_refs),
            timestamp,
            timestamp,
            analysis_mode,
            agent_provider,
        )

    def transition(self, status: TaskStatus | str, now: str | None = None) -> AnalysisTask:
        target = TaskStatus(status)
        if self.status == TaskStatus.ARCHIVED or target == self.status:
            raise WorkspaceContractError(f"invalid task status transition: {self.status.value} -> {target.value}")
        return replace(self, status=target, updated_at=now or _utc_now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "task_id": self.task_id,
            "title": self.title,
            "goal": self.goal,
            "status": self.status.value,
            "snapshot_refs": [ref.to_dict() for ref in self.snapshot_refs],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "analysis_mode": self.analysis_mode,
            "agent_provider": self.agent_provider,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AnalysisTask:
        refs = payload.get("snapshot_refs", ())
        if not isinstance(refs, (list, tuple)):
            raise WorkspaceContractError("snapshot_refs must be a list")
        return cls(
            task_id=str(payload.get("task_id", "")),
            title=str(payload.get("title", "")),
            goal=str(payload.get("goal", "")),
            status=TaskStatus(str(payload.get("status", ""))),
            snapshot_refs=tuple(SnapshotRef.from_dict(ref) for ref in refs),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            analysis_mode=str(payload.get("analysis_mode", "demo")),
            agent_provider=str(payload["agent_provider"]) if payload.get("agent_provider") is not None else None,
            contract_version=_require_version(payload.get("contract_version")),
        )


_RUN_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.INTERRUPTED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.INTERRUPTED: set(),
}


@dataclass(frozen=True)
class AnalysisRun:
    run_id: str
    task_id: str
    status: RunStatus
    snapshot_refs: tuple[SnapshotRef, ...]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_version(self.contract_version)
        _require_identifier(self.run_id, "run_id")
        _require_identifier(self.task_id, "task_id")
        object.__setattr__(self, "status", RunStatus(self.status))
        object.__setattr__(self, "snapshot_refs", _snapshot_refs(self.snapshot_refs))
        _require_timestamp(self.created_at, "created_at")
        if self.started_at is not None:
            _require_timestamp(self.started_at, "started_at")
        if self.completed_at is not None:
            _require_timestamp(self.completed_at, "completed_at")

    @classmethod
    def create(
        cls,
        run_id: str,
        task_id: str,
        snapshot_refs: Iterable[SnapshotRef] = (),
        now: str | None = None,
    ) -> AnalysisRun:
        return cls(run_id, task_id, RunStatus.QUEUED, tuple(snapshot_refs), now or _utc_now())

    def transition(self, status: RunStatus | str, now: str | None = None) -> AnalysisRun:
        target = RunStatus(status)
        if target not in _RUN_TRANSITIONS[self.status]:
            raise WorkspaceContractError(f"invalid run status transition: {self.status.value} -> {target.value}")
        timestamp = now or _utc_now()
        return replace(
            self,
            status=target,
            started_at=timestamp if target == RunStatus.RUNNING else self.started_at,
            completed_at=timestamp
            if target in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.INTERRUPTED}
            else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status.value,
            "snapshot_refs": [ref.to_dict() for ref in self.snapshot_refs],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AnalysisRun:
        refs = payload.get("snapshot_refs", ())
        if not isinstance(refs, (list, tuple)):
            raise WorkspaceContractError("snapshot_refs must be a list")
        return cls(
            run_id=str(payload.get("run_id", "")),
            task_id=str(payload.get("task_id", "")),
            status=RunStatus(str(payload.get("status", ""))),
            snapshot_refs=tuple(SnapshotRef.from_dict(ref) for ref in refs),
            created_at=str(payload.get("created_at", "")),
            started_at=None if payload.get("started_at") is None else str(payload["started_at"]),
            completed_at=None if payload.get("completed_at") is None else str(payload["completed_at"]),
            contract_version=_require_version(payload.get("contract_version")),
        )
