"""Bounded communication metadata for attributable Agent Flow handoffs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .workspace import WorkspaceContractError, _require_identifier, _require_timestamp


PROTOCOL_VERSION = 1
_FIELDS = frozenset(
    {
        "protocol_version",
        "message_id",
        "trace_id",
        "causation_id",
        "sender",
        "receiver",
        "attempt",
        "idempotency_key",
        "deadline_at",
    }
)


class AgentProtocolError(ValueError):
    """Raised when public communication metadata is unsafe or ambiguous."""


@dataclass(frozen=True)
class CommunicationEnvelope:
    message_id: str
    trace_id: str
    causation_id: str | None
    sender: str
    receiver: str
    attempt: int
    idempotency_key: str
    deadline_at: str | None = None
    protocol_version: int = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise AgentProtocolError(f"unsupported protocol_version: {self.protocol_version!r}")
        try:
            _require_identifier(self.message_id, "message_id")
            _require_identifier(self.trace_id, "trace_id")
            if self.causation_id is not None:
                _require_identifier(self.causation_id, "causation_id")
            _require_identifier(self.sender, "sender")
            _require_identifier(self.receiver, "receiver")
            _require_identifier(self.idempotency_key, "idempotency_key")
            if self.deadline_at is not None:
                _require_timestamp(self.deadline_at, "deadline_at")
        except WorkspaceContractError as exc:
            raise AgentProtocolError(str(exc)) from exc
        if not isinstance(self.attempt, int) or isinstance(self.attempt, bool) or not 1 <= self.attempt <= 100:
            raise AgentProtocolError("attempt must be an integer between 1 and 100")

    @classmethod
    def create(
        cls,
        *,
        message_id: str,
        trace_id: str,
        sender: str,
        receiver: str,
        attempt: int,
        idempotency_key: str,
        causation_id: str | None = None,
        deadline_at: str | None = None,
    ) -> CommunicationEnvelope:
        return cls(
            message_id=message_id,
            trace_id=trace_id,
            causation_id=causation_id,
            sender=sender,
            receiver=receiver,
            attempt=attempt,
            idempotency_key=idempotency_key,
            deadline_at=deadline_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "protocol_version": self.protocol_version,
            "message_id": self.message_id,
            "trace_id": self.trace_id,
            "causation_id": self.causation_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "attempt": self.attempt,
            "idempotency_key": self.idempotency_key,
            "deadline_at": self.deadline_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CommunicationEnvelope:
        if not isinstance(payload, Mapping) or set(payload) != _FIELDS:
            raise AgentProtocolError("communication envelope fields do not match the protocol")
        return cls(
            message_id=str(payload.get("message_id", "")),
            trace_id=str(payload.get("trace_id", "")),
            causation_id=_optional_text(payload.get("causation_id")),
            sender=str(payload.get("sender", "")),
            receiver=str(payload.get("receiver", "")),
            attempt=payload.get("attempt"),
            idempotency_key=str(payload.get("idempotency_key", "")),
            deadline_at=_optional_text(payload.get("deadline_at")),
            protocol_version=payload.get("protocol_version"),
        )


def legacy_communication(run_id: str, sequence: int, kind: str) -> CommunicationEnvelope:
    """Create stable metadata when reading an event persisted before protocol v1."""

    return CommunicationEnvelope.create(
        message_id=_stable_identifier("msg", run_id, str(sequence)),
        trace_id=run_id,
        sender="orchestrator",
        receiver="workbench",
        attempt=1,
        idempotency_key=_stable_identifier("event", run_id, str(sequence), kind),
    )


def event_communication(
    run_id: str,
    sequence: int,
    kind: str,
    summary: Mapping[str, object],
    artifact_refs: tuple[str, ...],
    *,
    planner_source: str,
    causation_id: str | None,
) -> CommunicationEnvelope:
    """Build the public delivery envelope for one persisted execution event."""

    sender, receiver = _route(kind, summary, planner_source)
    attempt = summary.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        attempt = 1
    deadline_at = summary.get("deadline_at")
    if not isinstance(deadline_at, str):
        deadline_at = None
    delivery = json.dumps(
        {
            "run_id": run_id,
            "sequence": sequence,
            "kind": kind,
            "summary": dict(summary),
            "artifact_refs": list(artifact_refs),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(delivery.encode("utf-8")).hexdigest()
    return CommunicationEnvelope.create(
        message_id=_stable_identifier("msg", run_id, str(sequence)),
        trace_id=run_id,
        causation_id=causation_id,
        sender=sender,
        receiver=receiver,
        attempt=attempt,
        idempotency_key=f"delivery-{digest}",
        deadline_at=deadline_at,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AgentProtocolError("optional communication identifiers must be strings")
    return value


def _stable_identifier(prefix: str, *parts: str) -> str:
    candidate = "-".join((prefix, *parts))
    if len(candidate) <= 200:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest}"


def _route(kind: str, summary: Mapping[str, object], planner_source: str) -> tuple[str, str]:
    tool = summary.get("tool")
    tool_actor = f"tool.{tool}" if isinstance(tool, str) and tool else "tool.analysis"
    if kind == "round.planned" or kind.startswith("planner."):
        source = summary.get("planner")
        if not isinstance(source, str) or not source:
            source = planner_source
        return f"planner.{source}", "orchestrator"
    if kind in {"step.started", "tool.started"}:
        return "orchestrator", tool_actor
    if kind in {"tool.result", "tool.failed"}:
        return tool_actor, "orchestrator"
    if kind == "artifact.created":
        return tool_actor, "evidence_store"
    if kind in {
        "node.added",
        "node.updated",
        "edge.added",
        "edge.activated",
        "evidence.linked",
        "conflict.detected",
        "knowledge.candidate",
        "knowledge.verified",
        "knowledge.superseded",
    }:
        return "orchestrator", "evidence_store"
    if kind == "report.generated":
        return "reporter", "workbench"
    return "orchestrator", "workbench"
