"""Host-owned observable orchestration for deterministic workbench runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import secrets
from typing import Any

from .data_profile import DataProfile, build_default_dashboard, profile_standard_csv
from .dashboard import DashboardSpec
from .documents import build_document_corpus
from .evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from .run_events import RunEvent
from .text_dashboard import TextDashboard, build_text_dashboard
from .workspace import AnalysisRun, AnalysisTask, RunStatus
from .workspace_store import WorkspaceStore


@dataclass(frozen=True)
class OrchestrationResult:
    run: AnalysisRun
    events: tuple[RunEvent, ...]
    data_profile: DataProfile
    dashboard: DashboardSpec
    text_dashboard: TextDashboard
    evidence_graph: EvidenceGraph


class AnalysisOrchestrator:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        proposal: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        run = AnalysisRun.create(f"run-{secrets.token_hex(12)}", task.task_id, task.snapshot_refs).transition(RunStatus.RUNNING)
        events: list[RunEvent] = []

        def emit(kind: str, phase: str, summary: dict[str, object], refs: tuple[str, ...] = ()) -> None:
            event = RunEvent.create(run.run_id, len(events) + 1, kind, phase, summary, refs)
            if events:
                self.store.append_event(event)
            else:
                self.store.create_run(run, event)
            events.append(event)

        emit("run.started", "setup", {"snapshot_count": len(run.snapshot_refs)})
        try:
            dataset = next((ref for ref in run.snapshot_refs if ref.kind == "dataset"), None)
            if dataset is None:
                raise ValueError("analysis run requires a dataset snapshot")
            hypotheses = _parse_hypotheses(proposal)
            profile = profile_standard_csv(data_path, dataset.snapshot_id)
            emit("data.profiled", "profile", {"row_count": profile.row_count, "metric_count": len(profile.metrics)})
            dashboard = build_default_dashboard(profile)
            emit("chart.spec.created", "dashboard", {"block_count": len(dashboard.blocks)}, (dashboard.dashboard_id,))
            corpus = build_document_corpus(document_paths, f"corpus-{run.run_id}")
            text_dashboard = build_text_dashboard(corpus)
            emit("document.indexed", "documents", {"document_count": text_dashboard.document_count, "failure_count": text_dashboard.failure_count})
            for claim in text_dashboard.claims:
                emit("claim.extracted", "documents", {"claim_id": claim.claim_id, "status": claim.status}, (claim.claim_id,))
            for hypothesis_id, text in hypotheses:
                emit("hypothesis.created", "hypotheses", {"hypothesis_id": hypothesis_id, "status": "pending"}, (hypothesis_id,))
                emit(
                    "validation.completed",
                    "validation",
                    {"hypothesis_id": hypothesis_id, "status": "insufficient"},
                    (hypothesis_id,),
                )
            graph = _build_graph(run.run_id, dataset.snapshot_id, dashboard.dashboard_id, text_dashboard, hypotheses)
            emit("evidence.linked", "evidence", {"node_count": len(graph.nodes), "edge_count": len(graph.edges)}, (graph.graph_id,))
            completed = run.transition(RunStatus.COMPLETED)
            emit("run.completed", "finish", {"status": completed.status.value})
            self.store.save_run(completed)
            return OrchestrationResult(completed, tuple(events), profile, dashboard, text_dashboard, graph)
        except Exception as exc:
            emit("run.failed", "finish", {"error_type": type(exc).__name__})
            self.store.save_run(run.transition(RunStatus.FAILED))
            raise


def _build_graph(
    run_id: str,
    dataset_id: str,
    dashboard_id: str,
    text: TextDashboard,
    hypotheses: tuple[tuple[str, str], ...],
) -> EvidenceGraph:
    nodes = [
        EvidenceNode("data-source", "data_source", "数据快照", "verified", dataset_id),
        EvidenceNode("data-signal", "data_signal", "数据画像", "verified", dashboard_id),
    ]
    edges = [EvidenceEdge("edge-data", "data-source", "data-signal", "derived_from")]
    claim_nodes = {}
    for index, claim in enumerate(text.claims):
        node_id = f"claim-{index + 1}"
        claim_nodes[claim.claim_id] = node_id
        nodes.append(EvidenceNode(node_id, "claim", claim.text[:500], "pending", claim.claim_id))
        edges.append(EvidenceEdge(f"edge-claim-{index + 1}", node_id, "data-signal", "tests"))
    conflict_index = 0
    seen_conflicts = set()
    for claim in text.claims:
        for other_id in claim.conflicts_with:
            pair = tuple(sorted((claim.claim_id, other_id)))
            if pair in seen_conflicts:
                continue
            seen_conflicts.add(pair)
            conflict_index += 1
            edges.append(
                EvidenceEdge(
                    f"edge-conflict-{conflict_index}",
                    claim_nodes[claim.claim_id],
                    claim_nodes[other_id],
                    "contradicts",
                )
            )
    for index, (hypothesis_id, hypothesis_text) in enumerate(hypotheses):
        nodes.append(EvidenceNode(hypothesis_id, "hypothesis", hypothesis_text, "pending"))
        validation_id = f"validation-{index + 1}"
        nodes.append(EvidenceNode(validation_id, "validation", "当前证据不足", "insufficient"))
        edges.append(EvidenceEdge(f"edge-hypothesis-{index + 1}", validation_id, hypothesis_id, "tests"))
        edges.append(EvidenceEdge(f"edge-insufficient-{index + 1}", "data-signal", validation_id, "insufficient_for"))
    return EvidenceGraph(f"graph-{run_id}", tuple(nodes), tuple(edges))


def _parse_hypotheses(proposal: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if proposal is None:
        return ()
    if not isinstance(proposal, dict) or set(proposal) != {"hypotheses"}:
        raise ValueError("agent proposal may contain only structured hypotheses")
    raw = proposal["hypotheses"]
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValueError("agent proposal hypotheses must be a bounded list")
    parsed = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"hypothesis_id", "text"}:
            raise ValueError("each hypothesis requires only hypothesis_id and text")
        node = EvidenceNode(str(item["hypothesis_id"]), "hypothesis", str(item["text"]), "pending")
        parsed.append((node.node_id, node.label))
    return tuple(parsed)
