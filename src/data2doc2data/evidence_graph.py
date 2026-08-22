"""Versioned evidence and hypothesis graph contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
NODE_TYPES = frozenset({"data_source", "compute_plan", "metric", "data_signal", "document_source", "document_excerpt", "claim", "hypothesis", "validation", "conclusion", "action"})
RELATIONSHIPS = frozenset({"derived_from", "supports", "contradicts", "tests", "insufficient_for"})
STATUSES = frozenset({"pending", "verified", "supported", "contradicted", "insufficient"})


class EvidenceGraphError(ValueError):
    pass


def _identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise EvidenceGraphError(f"{field} must be a stable identifier")


@dataclass(frozen=True)
class EvidenceNode:
    node_id: str
    kind: str
    label: str
    status: str
    artifact_ref: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.node_id, "node_id")
        if self.kind not in NODE_TYPES:
            raise EvidenceGraphError("unsupported node type")
        if self.status not in STATUSES:
            raise EvidenceGraphError("unsupported node status")
        if not isinstance(self.label, str) or not self.label.strip() or len(self.label) > 500:
            raise EvidenceGraphError("node label must be bounded text")
        if self.artifact_ref is not None:
            _identifier(self.artifact_ref, "artifact_ref")

    def to_dict(self) -> dict[str, object]:
        return {"node_id": self.node_id, "kind": self.kind, "label": self.label, "status": self.status, "artifact_ref": self.artifact_ref}


@dataclass(frozen=True)
class EvidenceEdge:
    edge_id: str
    source: str
    target: str
    relationship: str

    def __post_init__(self) -> None:
        for value, field in ((self.edge_id, "edge_id"), (self.source, "source"), (self.target, "target")):
            _identifier(value, field)
        if self.relationship not in RELATIONSHIPS:
            raise EvidenceGraphError("unsupported evidence relationship")

    def to_dict(self) -> dict[str, str]:
        return {"edge_id": self.edge_id, "source": self.source, "target": self.target, "relationship": self.relationship}


@dataclass(frozen=True)
class EvidenceGraph:
    graph_id: str
    nodes: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...]
    contract_version: int = 1

    def __post_init__(self) -> None:
        _identifier(self.graph_id, "graph_id")
        if self.contract_version != 1:
            raise EvidenceGraphError("unsupported graph contract version")
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise EvidenceGraphError("node IDs must be unique")
        if any(edge.source not in node_ids or edge.target not in node_ids for edge in self.edges):
            raise EvidenceGraphError("edge references a missing node")

    def to_dict(self) -> dict[str, object]:
        return {"contract_version": self.contract_version, "graph_id": self.graph_id, "nodes": [node.to_dict() for node in self.nodes], "edges": [edge.to_dict() for edge in self.edges]}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EvidenceGraph:
        return cls(
            str(payload.get("graph_id", "")),
            tuple(EvidenceNode(**item) for item in payload.get("nodes", ())),
            tuple(EvidenceEdge(**item) for item in payload.get("edges", ())),
            payload.get("contract_version"),
        )
