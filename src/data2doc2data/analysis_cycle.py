"""Immutable contracts for a host-controlled, maximum-three-round analysis loop."""

from __future__ import annotations

from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Mapping

from .workspace import WorkspaceContractError, _require_identifier


MAX_CYCLE_ROUNDS = 3
MAX_DECISION_ARGUMENT_BYTES = 2_048
_FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {"raw", "raw_data", "raw_rows", "row", "rows", "records", "code", "command", "shell", "chain_of_thought"}
)


class CyclePlanError(ValueError):
    """Raised when a cycle or planner decision violates the public contract."""


@dataclass(frozen=True)
class EvidenceGap:
    gap_id: str
    description: str
    suggested_tool: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.gap_id, "gap_id")
        if not self.description.strip() or len(self.description) > 500:
            raise CyclePlanError("evidence gap description must be bounded text")

    def to_dict(self) -> dict[str, object]:
        return {
            "gap_id": self.gap_id,
            "description": self.description,
            "suggested_tool": self.suggested_tool,
        }


@dataclass(frozen=True)
class RoundDecision:
    round_number: int
    action: str
    tool: str | None
    arguments: Mapping[str, object]
    rationale_summary: str
    prior_artifact_refs: tuple[str, ...] = ()
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    stop_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        object.__setattr__(self, "prior_artifact_refs", tuple(self.prior_artifact_refs))
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))

    def to_dict(self) -> dict[str, object]:
        return {
            "round_number": self.round_number,
            "action": self.action,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "rationale_summary": self.rationale_summary,
            "prior_artifact_refs": list(self.prior_artifact_refs),
            "evidence_gaps": [gap.to_dict() for gap in self.evidence_gaps],
            "stop_reason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RoundDecision:
        gaps = payload.get("evidence_gaps", [])
        if not isinstance(gaps, list):
            raise CyclePlanError("evidence_gaps must be a list")
        arguments = payload.get("arguments", {})
        refs = payload.get("prior_artifact_refs", [])
        if not isinstance(arguments, Mapping) or not isinstance(refs, list):
            raise CyclePlanError("round decision arguments or artifact refs are invalid")
        return cls(
            int(payload.get("round_number", 0)),
            str(payload.get("action", "")),
            str(payload["tool"]) if payload.get("tool") is not None else None,
            dict(arguments),
            str(payload.get("rationale_summary", "")),
            tuple(str(ref) for ref in refs),
            tuple(
                EvidenceGap(str(item.get("gap_id", "")), str(item.get("description", "")), item.get("suggested_tool"))
                for item in gaps
                if isinstance(item, Mapping)
            ),
            str(payload["stop_reason"]) if payload.get("stop_reason") is not None else None,
        )


@dataclass(frozen=True)
class AnalysisRound:
    round_number: int
    decision: RoundDecision
    artifact_refs: tuple[str, ...]
    status: str = "completed"
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_refs", tuple(self.artifact_refs))
        for ref in self.artifact_refs:
            _identifier(ref, "artifact_ref")

    @classmethod
    def completed(cls, decision: RoundDecision, artifact_refs: tuple[str, ...]) -> AnalysisRound:
        return cls(decision.round_number, decision, artifact_refs, "completed")

    def to_dict(self) -> dict[str, object]:
        return {
            "round_number": self.round_number,
            "decision": self.decision.to_dict(),
            "artifact_refs": list(self.artifact_refs),
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AnalysisRound:
        decision = payload.get("decision")
        refs = payload.get("artifact_refs", [])
        if not isinstance(decision, Mapping) or not isinstance(refs, list):
            raise CyclePlanError("analysis round payload is invalid")
        return cls(
            int(payload.get("round_number", 0)),
            RoundDecision.from_dict(decision),
            tuple(str(ref) for ref in refs),
            str(payload.get("status", "")),
            str(payload["error"]) if payload.get("error") is not None else None,
        )


@dataclass(frozen=True)
class AnalysisCycle:
    cycle_id: str
    status: str
    max_rounds: int
    rounds: tuple[AnalysisRound, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.cycle_id, "cycle_id")
        if not 1 <= self.max_rounds <= MAX_CYCLE_ROUNDS:
            raise CyclePlanError(f"cycle max_rounds must be between one and {MAX_CYCLE_ROUNDS}")
        if self.status not in {"running", "waiting_for_planner", "completed", "failed", "interrupted"}:
            raise CyclePlanError("cycle status is invalid")
        object.__setattr__(self, "rounds", tuple(self.rounds))

    @classmethod
    def start(cls, cycle_id: str, *, max_rounds: int = MAX_CYCLE_ROUNDS) -> AnalysisCycle:
        return cls(cycle_id, "running", max_rounds)

    @property
    def can_continue(self) -> bool:
        return self.status == "running" and len(self.rounds) < self.max_rounds

    @property
    def artifact_refs(self) -> tuple[str, ...]:
        return tuple(ref for analysis_round in self.rounds for ref in analysis_round.artifact_refs)

    def complete_round(self, analysis_round: AnalysisRound) -> AnalysisCycle:
        if not self.can_continue:
            raise CyclePlanError("analysis cycle cannot continue")
        expected = len(self.rounds) + 1
        if analysis_round.round_number != expected or analysis_round.decision.round_number != expected:
            raise CyclePlanError("analysis rounds must be contiguous")
        prior = set(self.artifact_refs)
        if expected > 1 and not set(analysis_round.decision.prior_artifact_refs) <= prior:
            raise CyclePlanError("revision must reference a prior artifact from this cycle")
        if analysis_round.status != "completed":
            raise CyclePlanError("only completed rounds can advance a cycle")
        rounds = (*self.rounds, analysis_round)
        finished = analysis_round.decision.action == "finish" or len(rounds) >= self.max_rounds
        return AnalysisCycle(self.cycle_id, "completed" if finished else "running", self.max_rounds, rounds)

    def transition(self, status: str) -> AnalysisCycle:
        return AnalysisCycle(self.cycle_id, status, self.max_rounds, self.rounds)

    def to_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "status": self.status,
            "max_rounds": self.max_rounds,
            "rounds": [analysis_round.to_dict() for analysis_round in self.rounds],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AnalysisCycle:
        rounds = payload.get("rounds", [])
        if not isinstance(rounds, list):
            raise CyclePlanError("cycle rounds must be a list")
        return cls(
            str(payload.get("cycle_id", "")),
            str(payload.get("status", "")),
            int(payload.get("max_rounds", 0)),
            tuple(AnalysisRound.from_dict(item) for item in rounds if isinstance(item, Mapping)),
        )


def validate_round_decision(
    decision: RoundDecision,
    registered_tools: set[str] | frozenset[str],
    *,
    prior_decision: RoundDecision | None = None,
) -> RoundDecision:
    if not isinstance(decision.round_number, int) or isinstance(decision.round_number, bool) or decision.round_number < 1:
        raise CyclePlanError("round number must be a positive integer")
    if decision.action not in {"continue", "finish"}:
        raise CyclePlanError("round action must be continue or finish")
    if not decision.rationale_summary.strip() or len(decision.rationale_summary) > 500:
        raise CyclePlanError("rationale summary must be bounded public text")
    if decision.action == "finish":
        if decision.tool is not None or decision.arguments:
            raise CyclePlanError("finish decisions cannot invoke a tool")
        if not decision.stop_reason or len(decision.stop_reason) > 120:
            raise CyclePlanError("finish decisions require a bounded stop reason")
        return decision
    if decision.tool not in registered_tools:
        raise CyclePlanError("round decisions may use only a registered tool")
    if decision.stop_reason is not None:
        raise CyclePlanError("continue decisions cannot contain a stop reason")
    if decision.round_number > 1 and not decision.prior_artifact_refs:
        raise CyclePlanError("a revision requires at least one prior artifact reference")
    for ref in decision.prior_artifact_refs:
        _identifier(ref, "prior artifact reference")
    copied = dict(decision.arguments)
    if _contains_forbidden_key(copied):
        raise CyclePlanError("raw data, code, and commands are not allowed in round arguments")
    try:
        encoded = json.dumps(copied, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CyclePlanError("round arguments must be JSON serializable") from exc
    if len(encoded) > MAX_DECISION_ARGUMENT_BYTES:
        raise CyclePlanError("round arguments must remain bounded")
    if prior_decision is not None and decision.tool == prior_decision.tool and copied == dict(prior_decision.arguments):
        raise CyclePlanError("a later round must revise the tool or arguments")
    return decision


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _FORBIDDEN_ARGUMENT_KEYS or _contains_forbidden_key(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _identifier(value: str, field: str) -> None:
    try:
        _require_identifier(value, field)
    except WorkspaceContractError as exc:
        raise CyclePlanError(str(exc)) from exc
