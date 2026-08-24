"""Governed, project-scoped knowledge records with append-only state history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from .workspace import _require_identifier, _require_timestamp, _utc_now

if TYPE_CHECKING:
    from .workspace_store import WorkspaceStore


KNOWLEDGE_STATES = frozenset({"candidate", "verified", "superseded", "rejected"})


class KnowledgeError(ValueError):
    """Raised when knowledge would bypass evidence or governance rules."""


@dataclass(frozen=True)
class KnowledgeRecord:
    project_id: str
    knowledge_id: str
    revision: int
    statement: str
    state: str
    source_refs: tuple[str, ...]
    run_id: str
    evidence_refs: tuple[str, ...]
    created_at: str
    updated_at: str
    valid_from: str | None = None
    valid_to: str | None = None
    replacement_id: str | None = None
    decision_by: str | None = None
    decision_reason: str | None = None
    contract_version: int = 1

    def __post_init__(self) -> None:
        if self.contract_version != 1:
            raise KnowledgeError("unsupported knowledge contract version")
        try:
            _require_identifier(self.project_id, "project_id")
            _require_identifier(self.knowledge_id, "knowledge_id")
            _require_identifier(self.run_id, "run_id")
            for ref in (*self.source_refs, *self.evidence_refs):
                _require_identifier(ref, "knowledge reference")
            if self.replacement_id is not None:
                _require_identifier(self.replacement_id, "replacement_id")
            _require_timestamp(self.created_at, "created_at")
            _require_timestamp(self.updated_at, "updated_at")
            if self.valid_from is not None:
                _require_timestamp(self.valid_from, "valid_from")
            if self.valid_to is not None:
                _require_timestamp(self.valid_to, "valid_to")
        except ValueError as exc:
            raise KnowledgeError(str(exc)) from exc
        if not isinstance(self.revision, int) or isinstance(self.revision, bool) or self.revision < 1:
            raise KnowledgeError("knowledge revision must be positive")
        if self.state not in KNOWLEDGE_STATES:
            raise KnowledgeError("unsupported knowledge state")
        if not isinstance(self.statement, str) or not self.statement.strip() or len(self.statement) > 1000:
            raise KnowledgeError("knowledge statement must be bounded text")
        if len(self.source_refs) > 100 or len(self.evidence_refs) > 100:
            raise KnowledgeError("knowledge provenance must be bounded")
        if not self.source_refs:
            raise KnowledgeError("knowledge requires at least one source reference")
        for value, field, limit in (
            (self.decision_by, "decision_by", 200),
            (self.decision_reason, "decision_reason", 1000),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > limit):
                raise KnowledgeError(f"{field} must be bounded text")
        if datetime.fromisoformat(self.updated_at) < datetime.fromisoformat(self.created_at):
            raise KnowledgeError("knowledge timestamps are out of order")
        if self.valid_from is not None and self.valid_to is not None:
            if datetime.fromisoformat(self.valid_to) < datetime.fromisoformat(self.valid_from):
                raise KnowledgeError("knowledge validity interval is out of order")
        if self.state == "candidate" and any(
            value is not None
            for value in (
                self.valid_from,
                self.valid_to,
                self.replacement_id,
                self.decision_by,
                self.decision_reason,
            )
        ):
            raise KnowledgeError("candidate knowledge cannot contain a decision")
        if self.state == "verified" and (self.valid_from is None or self.decision_by is None):
            raise KnowledgeError("verified knowledge requires validity and approval")
        if self.state == "verified" and any(value is not None for value in (self.valid_to, self.replacement_id)):
            raise KnowledgeError("verified knowledge cannot already be superseded")
        if self.state == "superseded" and (
            self.valid_from is None or self.valid_to is None or self.replacement_id is None or self.decision_by is None
        ):
            raise KnowledgeError("superseded knowledge requires a replacement and validity interval")
        if self.state == "rejected" and self.decision_by is None:
            raise KnowledgeError("rejected knowledge requires explicit approval")
        if self.state == "rejected" and any(
            value is not None for value in (self.valid_from, self.valid_to, self.replacement_id)
        ):
            raise KnowledgeError("rejected knowledge cannot have a validity interval")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "project_id": self.project_id,
            "knowledge_id": self.knowledge_id,
            "revision": self.revision,
            "statement": self.statement,
            "state": self.state,
            "source_refs": list(self.source_refs),
            "run_id": self.run_id,
            "evidence_refs": list(self.evidence_refs),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "replacement_id": self.replacement_id,
            "decision_by": self.decision_by,
            "decision_reason": self.decision_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> KnowledgeRecord:
        source_refs = payload.get("source_refs", ())
        evidence_refs = payload.get("evidence_refs", ())
        if not isinstance(source_refs, (list, tuple)) or not isinstance(evidence_refs, (list, tuple)):
            raise KnowledgeError("knowledge references must be lists")
        return cls(
            project_id=str(payload.get("project_id", "")),
            knowledge_id=str(payload.get("knowledge_id", "")),
            revision=payload.get("revision"),
            statement=str(payload.get("statement", "")),
            state=str(payload.get("state", "")),
            source_refs=tuple(str(item) for item in source_refs),
            run_id=str(payload.get("run_id", "")),
            evidence_refs=tuple(str(item) for item in evidence_refs),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            valid_from=payload.get("valid_from"),
            valid_to=payload.get("valid_to"),
            replacement_id=payload.get("replacement_id"),
            decision_by=payload.get("decision_by"),
            decision_reason=payload.get("decision_reason"),
            contract_version=payload.get("contract_version"),
        )


class KnowledgeLedger:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def propose(
        self,
        project_id: str,
        knowledge_id: str,
        statement: str,
        source_refs: tuple[str, ...],
        run_id: str,
        evidence_refs: tuple[str, ...],
        now: str | None = None,
    ) -> KnowledgeRecord:
        timestamp = now or _utc_now()
        record = KnowledgeRecord(
            project_id,
            knowledge_id,
            1,
            statement,
            "candidate",
            tuple(source_refs),
            run_id,
            tuple(evidence_refs),
            timestamp,
            timestamp,
        )
        try:
            return self.store.append_knowledge_version(record)
        except ValueError as exc:
            raise KnowledgeError(str(exc)) from exc

    def verify(
        self,
        project_id: str,
        knowledge_id: str,
        approved_by: str,
        deterministic_verified: bool,
        evidence_refs: tuple[str, ...] = (),
        now: str | None = None,
    ) -> KnowledgeRecord:
        if deterministic_verified is not True:
            raise KnowledgeError("deterministic verification is required")
        if not isinstance(approved_by, str) or not approved_by.strip():
            raise KnowledgeError("explicit approval is required")
        current = self._current(project_id, knowledge_id, "candidate")
        combined_evidence = tuple(dict.fromkeys((*current.evidence_refs, *evidence_refs)))
        if not combined_evidence:
            raise KnowledgeError("deterministic verification requires evidence references")
        timestamp = now or _utc_now()
        verified = KnowledgeRecord(
            project_id=current.project_id,
            knowledge_id=current.knowledge_id,
            revision=current.revision + 1,
            statement=current.statement,
            state="verified",
            source_refs=current.source_refs,
            run_id=current.run_id,
            evidence_refs=combined_evidence,
            created_at=current.created_at,
            updated_at=timestamp,
            valid_from=timestamp,
            decision_by=approved_by.strip(),
        )
        return self.store.append_knowledge_version(verified)

    def reject(
        self,
        project_id: str,
        knowledge_id: str,
        approved_by: str,
        reason: str,
        now: str | None = None,
    ) -> KnowledgeRecord:
        current = self._current(project_id, knowledge_id, "candidate")
        timestamp = now or _utc_now()
        rejected = KnowledgeRecord(
            project_id=current.project_id,
            knowledge_id=current.knowledge_id,
            revision=current.revision + 1,
            statement=current.statement,
            state="rejected",
            source_refs=current.source_refs,
            run_id=current.run_id,
            evidence_refs=current.evidence_refs,
            created_at=current.created_at,
            updated_at=timestamp,
            decision_by=approved_by,
            decision_reason=reason,
        )
        return self.store.append_knowledge_version(rejected)

    def supersede(
        self,
        project_id: str,
        knowledge_id: str,
        replacement_id: str,
        approved_by: str,
        reason: str,
        now: str | None = None,
    ) -> KnowledgeRecord:
        if knowledge_id == replacement_id:
            raise KnowledgeError("replacement knowledge must be different")
        current = self._current(project_id, knowledge_id, "verified")
        replacement = self._current(project_id, replacement_id, "verified")
        timestamp = now or _utc_now()
        superseded = KnowledgeRecord(
            project_id=current.project_id,
            knowledge_id=current.knowledge_id,
            revision=current.revision + 1,
            statement=current.statement,
            state="superseded",
            source_refs=current.source_refs,
            run_id=current.run_id,
            evidence_refs=tuple(dict.fromkeys((*current.evidence_refs, *replacement.evidence_refs))),
            created_at=current.created_at,
            updated_at=timestamp,
            valid_from=current.valid_from,
            valid_to=timestamp,
            replacement_id=replacement.knowledge_id,
            decision_by=approved_by,
            decision_reason=reason,
        )
        return self.store.append_knowledge_version(superseded)

    def latest(self, project_id: str) -> tuple[KnowledgeRecord, ...]:
        return self.store.list_latest_knowledge(project_id)

    def verified_facts(self, project_id: str) -> tuple[KnowledgeRecord, ...]:
        return tuple(record for record in self.latest(project_id) if record.state == "verified")

    def history(self, project_id: str, knowledge_id: str) -> tuple[KnowledgeRecord, ...]:
        return self.store.knowledge_history(project_id, knowledge_id)

    def _current(self, project_id: str, knowledge_id: str, expected_state: str) -> KnowledgeRecord:
        history = self.history(project_id, knowledge_id)
        if not history:
            raise KnowledgeError("knowledge record was not found in this project")
        current = history[-1]
        if current.state != expected_state:
            raise KnowledgeError(f"knowledge must be {expected_state} for this decision")
        return current
