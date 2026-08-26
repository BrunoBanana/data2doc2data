"""Bounded dual-runner execution for observable data and text reasoning flows."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
from time import perf_counter
from typing import Any

from .agent_protocol import event_communication
from .data_profile import DataProfile, build_default_dashboard, profile_standard_csv
from .artifacts import ArtifactStore
from .cycle_runner import ConnectedCycleRunner, DemoCycleRunner
from .dashboard import DashboardSpec
from .dashboard import build_artifact_dashboard
from .documents import build_document_corpus
from .evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceNode, build_cycle_evidence_graph
from .flow_tools import LocalAnalysisTools, REGISTERED_ANALYSIS_TOOLS, ToolResult
from .knowledge import KnowledgeLedger
from .reporting import build_html_report
from .run_events import RunEvent
from .text_dashboard import TextDashboard, build_text_dashboard
from .workspace import AnalysisRun, AnalysisTask, RunStatus
from .workspace_store import WorkspaceStore


MAX_FLOW_STEPS = 32
MAX_PLAN_REVISIONS = 3
MAX_ARGUMENT_BYTES = 2048
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {"code", "command", "shell", "script", "raw", "raw_data", "rows", "records", "chain_of_thought"}
)


class FlowPlanError(ValueError):
    """Raised when a connected agent proposes an unsafe or invalid flow."""


class FlowCancelled(RuntimeError):
    """Raised at a safe tool boundary when a user cancels a running flow."""


@dataclass(frozen=True)
class FlowStep:
    step_id: str
    tool: str
    purpose: str
    dependencies: tuple[str, ...]
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class FlowPlan:
    plan_id: str
    steps: tuple[FlowStep, ...]
    runner: str = "connected"


@dataclass(frozen=True)
class FlowHypothesis:
    hypothesis_id: str
    text: str
    tool_payload: Mapping[str, object] | None = None


@dataclass(frozen=True)
class FlowExecutionResult:
    run: AnalysisRun
    events: tuple[RunEvent, ...]
    data_profile: DataProfile
    dashboard: DashboardSpec
    text_dashboard: TextDashboard
    evidence_graph: EvidenceGraph


def validate_flow_plan(payload: object, registered_tools: Iterable[str]) -> FlowPlan:
    """Validate a model-authored plan without allowing code or arbitrary I/O."""

    if not isinstance(payload, Mapping) or set(payload) != {"plan_id", "steps"}:
        raise FlowPlanError("flow plan requires only plan_id and steps")
    plan_id = str(payload["plan_id"])
    _require_identifier(plan_id, "plan_id")
    raw_steps = payload["steps"]
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= MAX_FLOW_STEPS:
        raise FlowPlanError(f"flow plan must contain between 1 and {MAX_FLOW_STEPS} steps")
    allowed = frozenset(registered_tools)
    parsed: list[FlowStep] = []
    seen: set[str] = set()
    for raw in raw_steps:
        required = {"step_id", "tool", "purpose", "dependencies", "arguments"}
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise FlowPlanError("each flow step must use the bounded step contract")
        step_id = str(raw["step_id"])
        tool = str(raw["tool"])
        purpose = str(raw["purpose"]).strip()
        _require_identifier(step_id, "step_id")
        if step_id in seen:
            raise FlowPlanError("flow step IDs must be unique")
        if tool not in allowed:
            raise FlowPlanError(f"flow steps may use only a registered tool: {tool}")
        if not purpose or len(purpose) > 300:
            raise FlowPlanError("step purpose must be bounded text")
        raw_dependencies = raw["dependencies"]
        if not isinstance(raw_dependencies, list) or len(raw_dependencies) > MAX_FLOW_STEPS:
            raise FlowPlanError("step dependencies must be a bounded list")
        dependencies = tuple(str(item) for item in raw_dependencies)
        for dependency in dependencies:
            _require_identifier(dependency, "dependency")
        arguments = raw["arguments"]
        if not isinstance(arguments, Mapping):
            raise FlowPlanError("step arguments must be an object")
        copied_arguments = dict(arguments)
        if _has_forbidden_argument(copied_arguments):
            raise FlowPlanError("step arguments cannot contain code, commands, or raw records")
        try:
            encoded = json.dumps(copied_arguments, ensure_ascii=False, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise FlowPlanError("step arguments must be JSON serializable") from exc
        if len(encoded) > MAX_ARGUMENT_BYTES:
            raise FlowPlanError("step arguments are too large")
        parsed.append(FlowStep(step_id, tool, purpose, dependencies, copied_arguments))
        seen.add(step_id)
    if any(dependency not in seen for step in parsed for dependency in step.dependencies):
        raise FlowPlanError("step dependencies must reference plan steps")
    if not _is_acyclic(parsed):
        raise FlowPlanError("flow plan must be acyclic")
    return FlowPlan(plan_id, tuple(parsed))


class DemoFlowRunner:
    """Run the complete local analysis journey without requiring a model."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        proposal: dict[str, Any] | None = None,
        *,
        on_event: Callable[[RunEvent], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> FlowExecutionResult:
        plan = _demo_plan(bool(document_paths), bool(proposal))
        return AgentFlowEngine(self.store).execute(
            task,
            data_path,
            document_paths,
            plan,
            proposal=proposal,
            on_event=on_event,
            cancelled=cancelled,
        )


class ConnectedFlowRunner:
    """Execute a connected assistant's bounded plan through host-owned tools."""

    REGISTERED_TOOLS = REGISTERED_ANALYSIS_TOOLS

    def __init__(self, store: WorkspaceStore, cycle_planner=None) -> None:
        self.store = store
        self.cycle_planner = cycle_planner

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        plan_payload: object,
        proposal: dict[str, Any] | None = None,
        *,
        on_event: Callable[[RunEvent], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> FlowExecutionResult:
        plan = validate_flow_plan(plan_payload, self.REGISTERED_TOOLS)
        planned_tools = {step.tool for step in plan.steps}
        required = {"inspect_sources", "profile_data"}
        if document_paths:
            required.update({"extract_claims", "align_evidence"})
        missing = sorted(required - planned_tools)
        if missing:
            raise FlowPlanError(f"connected plan is missing required tools: {', '.join(missing)}")
        return AgentFlowEngine(self.store).execute(
            task,
            data_path,
            document_paths,
            plan,
            proposal=proposal,
            on_event=on_event,
            cancelled=cancelled,
            connected_cycle_planner=self.cycle_planner,
        )


class AgentFlowEngine:
    """Project both runners onto the same persisted event and evidence protocol."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def execute(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        plan: FlowPlan,
        *,
        proposal: dict[str, Any] | None = None,
        on_event: Callable[[RunEvent], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        connected_cycle_planner=None,
    ) -> FlowExecutionResult:
        run = AnalysisRun.create(f"run-{secrets.token_hex(12)}", task.task_id, task.snapshot_refs).transition(
            RunStatus.RUNNING
        )
        events: list[RunEvent] = []
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []
        graph_id = f"graph-{run.run_id}"
        graph_revision = 0
        tool_commands: dict[str, str] = {}

        def emit(kind: str, phase: str, summary: Mapping[str, object], refs: tuple[str, ...] = ()) -> RunEvent:
            sequence = len(events) + 1
            step_id = summary.get("step_id")
            causation_id = events[-1].communication.message_id if events else None
            if kind in {"tool.result", "tool.failed"} and isinstance(step_id, str):
                causation_id = tool_commands.get(step_id, causation_id)
            communication = event_communication(
                run.run_id,
                sequence,
                kind,
                summary,
                refs,
                planner_source="connected_agent" if plan.runner == "connected" else "deterministic_demo",
                causation_id=causation_id,
            )
            event = RunEvent.create(
                run.run_id,
                sequence,
                kind,
                phase,
                summary,
                refs,
                communication=communication,
            )
            if events:
                self.store.append_event(event)
            else:
                self.store.create_run(run, event)
            events.append(event)
            if kind == "tool.started" and isinstance(step_id, str):
                tool_commands[step_id] = event.communication.message_id
            if on_event is not None:
                on_event(event)
            return event

        def graph() -> EvidenceGraph:
            return EvidenceGraph(graph_id, tuple(nodes), tuple(edges))

        def add_node(node: EvidenceNode, phase: str) -> None:
            nonlocal graph_revision
            nodes.append(node)
            current = graph()
            graph_revision = self.store.save_run_artifact(
                run.run_id,
                "evidence_graph",
                current.to_dict(),
                expected_revision=graph_revision,
            )
            emit(
                "node.added",
                phase,
                {"node_id": node.node_id, "node_kind": node.kind, "status": node.status, "label": node.label},
                tuple(ref for ref in (node.node_id, node.artifact_ref) if ref),
            )

        def add_edge(edge: EvidenceEdge, phase: str) -> None:
            nonlocal graph_revision
            edges.append(edge)
            current = graph()
            graph_revision = self.store.save_run_artifact(
                run.run_id,
                "evidence_graph",
                current.to_dict(),
                expected_revision=graph_revision,
            )
            summary = {
                "edge_id": edge.edge_id,
                "source": edge.source,
                "target": edge.target,
                "relationship": edge.relationship,
            }
            emit("edge.added", phase, summary, (edge.edge_id,))
            emit("edge.activated", phase, summary, (edge.edge_id,))

        def update_node(node_id: str, phase: str, *, status: str, label: str | None = None) -> None:
            nonlocal graph_revision
            for index, node in enumerate(nodes):
                if node.node_id != node_id:
                    continue
                updated = EvidenceNode(
                    node.node_id,
                    node.kind,
                    label if label is not None else node.label,
                    status,
                    node.artifact_ref,
                )
                nodes[index] = updated
                graph_revision = self.store.save_run_artifact(
                    run.run_id,
                    "evidence_graph",
                    graph().to_dict(),
                    expected_revision=graph_revision,
                )
                emit(
                    "node.updated",
                    phase,
                    {"node_id": updated.node_id, "status": updated.status, "label": updated.label},
                    tuple(ref for ref in (updated.node_id, updated.artifact_ref) if ref),
                )
                return
            raise ValueError(f"cannot update unknown evidence node: {node_id}")

        def check_cancelled() -> None:
            if cancelled is not None and cancelled():
                raise FlowCancelled("analysis run was cancelled")

        emit("run.started", "setup", {"snapshot_count": len(run.snapshot_refs), "runner": plan.runner})
        try:
            dataset = next((ref for ref in run.snapshot_refs if ref.kind == "dataset"), None)
            if dataset is None:
                raise ValueError("analysis run requires a dataset snapshot")
            cycle_result = None
            cycle_graph = None
            if plan.runner == "demo" or connected_cycle_planner is not None:
                cycle_id = f"cycle-{run.run_id}"
                emit("cycle.started", "cycle", {"cycle_id": cycle_id, "max_rounds": 3}, (cycle_id,))
                cycle_result = (
                    DemoCycleRunner(self.store).run(task, data_path, document_paths, cycle_id=cycle_id)
                    if connected_cycle_planner is None
                    else ConnectedCycleRunner(
                        self.store,
                        connected_cycle_planner,
                        on_planner_event=lambda kind, summary: emit(kind, "cycle", summary, (cycle_id,)),
                    ).run(
                        task, data_path, document_paths, cycle_id=cycle_id
                    )
                )
                if cycle_result.cycle.status != "completed":
                    raise RuntimeError(cycle_result.error or f"analysis cycle stopped: {cycle_result.cycle.status}")
                artifact_store = ArtifactStore(self.store.path.parent / "artifacts")
                artifact_dashboard = build_artifact_dashboard(cycle_result.cycle, artifact_store)
                cycle_graph = build_cycle_evidence_graph(cycle_result.cycle, artifact_store)
                self.store.save_run_artifact(run.run_id, "analysis_cycle", cycle_result.cycle.to_dict())
                self.store.save_run_artifact(run.run_id, "artifact_dashboard", artifact_dashboard.to_dict())
                for analysis_round in cycle_result.cycle.rounds:
                    decision = analysis_round.decision
                    emit(
                        "round.planned",
                        "cycle",
                        {
                            "cycle_id": cycle_id,
                            "round_number": analysis_round.round_number,
                            "action": decision.action,
                            "tool": decision.tool,
                            "rationale_summary": decision.rationale_summary,
                            "prior_artifact_refs": list(decision.prior_artifact_refs),
                            "planner": "connected_agent" if plan.runner == "connected" else "deterministic_demo",
                        },
                        (cycle_id, *decision.prior_artifact_refs),
                    )
                    emit(
                        "round.started",
                        "cycle",
                        {"cycle_id": cycle_id, "round_number": analysis_round.round_number, "tool": decision.tool},
                        (cycle_id,),
                    )
                    if decision.tool is not None:
                        emit(
                            "tool.started",
                            "cycle",
                            {
                                "step_id": f"cycle-round-{analysis_round.round_number}",
                                "tool": decision.tool,
                                "source": "connected_agent" if plan.runner == "connected" else "deterministic_demo",
                            },
                            (cycle_id,),
                        )
                    for artifact_ref in analysis_round.artifact_refs:
                        record = artifact_store.load(artifact_ref)
                        payload = record.get("payload", {})
                        emit(
                            "artifact.created",
                            "cycle",
                            {
                                "cycle_id": cycle_id,
                                "round_number": analysis_round.round_number,
                                "artifact_ref": artifact_ref,
                                "tool": decision.tool,
                                "kind": record.get("kind"),
                                "method": payload.get("method") if isinstance(payload, Mapping) else None,
                            },
                            (artifact_ref,),
                        )
                    if decision.tool is not None:
                        emit(
                            "tool.result",
                            "cycle",
                            {
                                "step_id": f"cycle-round-{analysis_round.round_number}",
                                "tool": decision.tool,
                                "artifact_count": len(analysis_round.artifact_refs),
                                "duration_ms": 0,
                            },
                            analysis_round.artifact_refs,
                        )
                    emit(
                        "round.completed",
                        "cycle",
                        {
                            "cycle_id": cycle_id,
                            "round_number": analysis_round.round_number,
                            "artifact_count": len(analysis_round.artifact_refs),
                        },
                        (cycle_id, *analysis_round.artifact_refs),
                    )
                emit(
                    "cycle.completed",
                    "cycle",
                    {
                        "cycle_id": cycle_id,
                        "status": cycle_result.cycle.status,
                        "round_count": len(cycle_result.cycle.rounds),
                    },
                    (cycle_id, *cycle_result.cycle.artifact_refs),
                )
            hypotheses = parse_hypotheses(proposal)
            emit(
                "plan.created",
                "planning",
                {
                    "plan_id": plan.plan_id,
                    "runner": plan.runner,
                    "step_count": len(plan.steps),
                    "revision_limit": MAX_PLAN_REVISIONS,
                },
                (plan.plan_id,),
            )
            for step in plan.steps:
                emit(
                    "step.added",
                    "planning",
                    {
                        "step_id": step.step_id,
                        "tool": step.tool,
                        "purpose": step.purpose,
                        "dependencies": list(step.dependencies),
                    },
                    (step.step_id,),
                )

            tools = LocalAnalysisTools(
                (data_path.parent, *(path.parent for path in document_paths)),
                artifact_store=ArtifactStore(self.store.path.parent / "artifacts"),
            )
            if plan.runner == "connected":
                for step in _ordered_steps(plan.steps):
                    check_cancelled()
                    _run_tool(
                        emit,
                        step.step_id,
                        step.tool,
                        lambda step=step: _invoke_connected_tool(
                            tools, step, data_path, dataset.snapshot_id, document_paths, f"corpus-{run.run_id}"
                        ),
                    )
            else:
                check_cancelled()
                _run_tool(
                    emit,
                    "inspect",
                    "inspect_sources",
                    lambda: tools.inspect_sources((data_path, *document_paths)),
                )

            check_cancelled()
            emit(
                "compute.plan.created",
                "compute",
                {"operation": "profile and aggregate", "fields": ["date", "metric", "value"], "row_limit": 1000},
            )
            if plan.runner == "demo":
                _run_tool(
                    emit,
                    "profile",
                    "profile_data",
                    lambda: tools.profile_data(data_path, dataset.snapshot_id),
                )
            profile = profile_standard_csv(data_path, dataset.snapshot_id)
            emit("data.profiled", "profile", {"row_count": profile.row_count, "metric_count": len(profile.metrics)})
            emit(
                "compute.result.created",
                "compute",
                {
                    "metric_count": len(profile.metrics),
                    "date_range": list(profile.date_range),
                    "quality_issue_count": profile.missing_count + profile.duplicate_count,
                },
            )
            dashboard = build_default_dashboard(profile)
            emit("chart.spec.created", "dashboard", {"block_count": len(dashboard.blocks)}, (dashboard.dashboard_id,))
            emit("dashboard.updated", "dashboard", {"block_count": len(dashboard.blocks)}, (dashboard.dashboard_id,))

            add_node(EvidenceNode("data-source", "data_source", "数据快照", "verified", dataset.snapshot_id), "sources")
            add_node(
                EvidenceNode("compute-plan", "compute_plan", "本地画像与聚合计划", "verified", dashboard.dashboard_id),
                "compute",
            )
            add_edge(EvidenceEdge("edge-data-plan", "data-source", "compute-plan", "derived_from"), "compute")
            add_node(
                EvidenceNode("data-signal", "data_signal", "数据画像", "verified", dashboard.dashboard_id), "compute"
            )
            add_edge(EvidenceEdge("edge-plan-signal", "compute-plan", "data-signal", "derived_from"), "compute")
            if cycle_graph is not None:
                for artifact_node in cycle_graph.nodes:
                    add_node(artifact_node, "cycle")
                for index, first_ref in enumerate(cycle_result.cycle.rounds[0].artifact_refs if cycle_result else ()):
                    add_edge(
                        EvidenceEdge(f"edge-cycle-source-{index + 1}", "data-signal", first_ref, "derived_from"),
                        "cycle",
                    )
                for cycle_edge in cycle_graph.edges:
                    add_edge(cycle_edge, "cycle")

            check_cancelled()
            corpus = build_document_corpus(document_paths, f"corpus-{run.run_id}")
            text_dashboard = build_text_dashboard(corpus)
            if document_paths and plan.runner == "demo":
                _run_tool(
                    emit,
                    "extract",
                    "extract_claims",
                    lambda: tools.extract_claims(document_paths, corpus.corpus_id),
                )
            emit(
                "document.indexed",
                "documents",
                {"document_count": text_dashboard.document_count, "failure_count": text_dashboard.failure_count},
            )
            emit(
                "retrieval.result.created",
                "documents",
                {
                    "section_count": sum(len(document.sections) for document in corpus.documents),
                    "claim_count": len(text_dashboard.claims),
                },
                (corpus.corpus_id,),
            )
            if text_dashboard.document_count:
                add_node(
                    EvidenceNode(
                        "document-source", "document_source", "文本材料", "verified", text_dashboard.corpus_id
                    ),
                    "documents",
                )
            claim_nodes: dict[str, str] = {}
            for index, claim in enumerate(text_dashboard.claims):
                emit(
                    "claim.extracted",
                    "documents",
                    {
                        "claim_id": claim.claim_id,
                        "status": claim.status,
                        "document": claim.citation.document,
                        "start_line": claim.citation.start_line,
                        "end_line": claim.citation.end_line,
                    },
                    (claim.claim_id,),
                )
                claim_id = f"claim-{index + 1}"
                excerpt_id = f"excerpt-{index + 1}"
                claim_nodes[claim.claim_id] = claim_id
                add_node(
                    EvidenceNode(
                        excerpt_id, "document_excerpt", claim.citation.excerpt[:500], "verified", claim.citation.sha256
                    ),
                    "documents",
                )
                add_edge(
                    EvidenceEdge(f"edge-excerpt-source-{index + 1}", "document-source", excerpt_id, "derived_from"),
                    "documents",
                )
                add_node(EvidenceNode(claim_id, "claim", claim.text[:500], "pending", claim.claim_id), "documents")
                add_edge(
                    EvidenceEdge(f"edge-claim-source-{index + 1}", excerpt_id, claim_id, "derived_from"), "documents"
                )
                add_edge(EvidenceEdge(f"edge-claim-{index + 1}", claim_id, "data-signal", "tests"), "cross-reasoning")

            if document_paths and plan.runner == "demo":
                _run_tool(
                    emit,
                    "align",
                    "align_evidence",
                    lambda: tools.align_evidence(data_path, dataset.snapshot_id, document_paths, corpus.corpus_id),
                )
            seen_conflicts: set[tuple[str, str]] = set()
            for claim in text_dashboard.claims:
                for other_id in claim.conflicts_with:
                    pair = tuple(sorted((claim.claim_id, other_id)))
                    if pair in seen_conflicts:
                        continue
                    seen_conflicts.add(pair)
                    edge = EvidenceEdge(
                        f"edge-conflict-{len(seen_conflicts)}",
                        claim_nodes[claim.claim_id],
                        claim_nodes[other_id],
                        "contradicts",
                    )
                    add_edge(edge, "cross-reasoning")
                    emit(
                        "conflict.detected",
                        "cross-reasoning",
                        {"left_claim_id": pair[0], "right_claim_id": pair[1], "relationship": "contradicts"},
                        (edge.edge_id,),
                    )
            if document_paths and not seen_conflicts:
                emit(
                    "plan.revised",
                    "cross-reasoning",
                    {"revision": 1, "reason": "文本主张需要与本地指标进行额外交叉核验", "added_tool": "align_evidence"},
                    (plan.plan_id,),
                )

            for index, hypothesis in enumerate(hypotheses):
                hypothesis_id = hypothesis.hypothesis_id
                emit(
                    "hypothesis.created",
                    "hypotheses",
                    {"hypothesis_id": hypothesis_id, "status": "pending"},
                    (hypothesis_id,),
                )
                add_node(EvidenceNode(hypothesis_id, "hypothesis", hypothesis.text, "pending"), "hypotheses")
                verification_status = "insufficient"
                verification_label = "当前证据不足"
                if hypothesis.tool_payload is not None:
                    result = _run_tool(
                        emit,
                        "hypotheses",
                        "test_hypothesis",
                        lambda payload=hypothesis.tool_payload: tools.test_hypothesis(
                            data_path, dataset.snapshot_id, payload
                        ),
                    )
                    observed_status = str(result.summary.get("status", "unavailable"))
                    verification_status = {
                        "confirmed": "supported",
                        "contradicted": "contradicted",
                        "unavailable": "insufficient",
                    }.get(observed_status, "insufficient")
                    verification_label = str(result.summary.get("summary", "当前证据不足"))[:500]
                validation_id = f"validation-{index + 1}"
                add_node(
                    EvidenceNode(validation_id, "validation", verification_label, verification_status), "validation"
                )
                add_edge(
                    EvidenceEdge(f"edge-hypothesis-{index + 1}", validation_id, hypothesis_id, "tests"), "validation"
                )
                evidence_relationship = {
                    "supported": "supports",
                    "contradicted": "contradicts",
                    "insufficient": "insufficient_for",
                }[verification_status]
                add_edge(
                    EvidenceEdge(
                        f"edge-validation-{index + 1}", "data-signal", validation_id, evidence_relationship
                    ),
                    "validation",
                )
                if hypothesis.tool_payload is not None:
                    update_node(hypothesis_id, "validation", status=verification_status)
                emit(
                    "validation.completed",
                    "validation",
                    {"hypothesis_id": hypothesis_id, "status": verification_status},
                    (hypothesis_id,),
                )

            hypothesis_nodes = [node for node in nodes if node.kind == "hypothesis"]
            supported_hypotheses = sum(node.status == "supported" for node in hypothesis_nodes)
            contradicted_hypotheses = sum(node.status == "contradicted" for node in hypothesis_nodes)
            insufficient_hypotheses = sum(node.status == "insufficient" for node in hypothesis_nodes)
            pending_hypotheses = sum(node.status == "pending" for node in hypothesis_nodes)
            if hypothesis_nodes:
                conclusion_label = (
                    f"{supported_hypotheses} 项假设获得数据支持，"
                    f"{contradicted_hypotheses} 项被反证，{insufficient_hypotheses} 项证据不足，"
                    f"{pending_hypotheses} 项待结构化。"
                )
            elif seen_conflicts:
                conclusion_label = f"文本材料中存在 {len(seen_conflicts)} 组冲突主张，需要复核口径。"
            else:
                conclusion_label = f"本地数据形成 {len(profile.metrics)} 个指标画像，尚未提出结构化业务假设。"
            add_node(EvidenceNode("analysis-conclusion", "conclusion", conclusion_label, "supported", graph_id), "delivery")
            add_edge(EvidenceEdge("edge-signal-conclusion", "data-signal", "analysis-conclusion", "supports"), "delivery")
            for index, validation in enumerate(node for node in nodes if node.kind == "validation"):
                relationship = {
                    "supported": "supports",
                    "contradicted": "contradicts",
                    "insufficient": "insufficient_for",
                }.get(validation.status, "derived_from")
                add_edge(
                    EvidenceEdge(
                        f"edge-validation-conclusion-{index + 1}",
                        validation.node_id,
                        "analysis-conclusion",
                        relationship,
                    ),
                    "delivery",
                )
            emit(
                "conclusion.created",
                "delivery",
                {
                    "conclusion_id": "analysis-conclusion",
                    "supported_hypotheses": supported_hypotheses,
                    "contradicted_hypotheses": contradicted_hypotheses,
                    "insufficient_hypotheses": insufficient_hypotheses,
                    "pending_hypotheses": pending_hypotheses,
                },
                ("analysis-conclusion", graph_id),
            )
            if contradicted_hypotheses or seen_conflicts:
                action_label = "优先复核被反证假设与冲突文本，再决定业务动作。"
            elif pending_hypotheses:
                action_label = "先把自然语言假设转换为指标、方向和时间窗口明确的可执行检验。"
            elif insufficient_hypotheses:
                action_label = "补充缺失指标或材料后，再运行证据核验。"
            else:
                action_label = "把已支持结论转为负责人、指标与复盘周期明确的行动项。"
            add_node(EvidenceNode("recommended-action", "action", action_label, "pending", graph_id), "delivery")
            add_edge(
                EvidenceEdge("edge-conclusion-action", "analysis-conclusion", "recommended-action", "derived_from"),
                "delivery",
            )
            if seen_conflicts:
                knowledge_statement = f"本次分析在文本材料中检测到 {len(seen_conflicts)} 组相互冲突的主张。"
            elif hypotheses:
                knowledge_statement = f"本次分析有 {len(hypotheses)} 个业务假设仍需补充证据。"
            else:
                knowledge_statement = f"本次本地分析形成 {len(profile.metrics)} 个指标的数据画像。"
            candidate = KnowledgeLedger(self.store).propose(
                project_id=task.task_id,
                knowledge_id=f"knowledge-{run.run_id}",
                statement=knowledge_statement,
                source_refs=tuple(ref.snapshot_id for ref in run.snapshot_refs),
                run_id=run.run_id,
                evidence_refs=(graph_id,),
            )
            emit(
                "knowledge.candidate",
                "knowledge",
                {
                    "knowledge_id": candidate.knowledge_id,
                    "state": candidate.state,
                    "statement": candidate.statement,
                    "requires_approval": True,
                },
                (candidate.knowledge_id, graph_id),
            )
            report = build_html_report(
                task,
                dashboard.to_dict(),
                text_dashboard.to_dict(),
                graph().to_dict(),
                run_count=len(self.store.list_runs(task.task_id)),
            )
            add_node(EvidenceNode("analysis-report", "report", report.filename, "verified", report.filename), "delivery")
            add_edge(
                EvidenceEdge("edge-action-report", "recommended-action", "analysis-report", "derived_from"),
                "delivery",
            )
            final_graph = graph()
            report = build_html_report(
                task,
                dashboard.to_dict(),
                text_dashboard.to_dict(),
                final_graph.to_dict(),
                run_count=len(self.store.list_runs(task.task_id)),
            )
            emit("evidence.linked", "evidence", {"node_count": len(nodes), "edge_count": len(edges)}, (graph_id,))
            emit(
                "report.generated",
                "report",
                {
                    "filename": report.filename,
                    "byte_count": len(report.html.encode("utf-8")),
                    "sha256": hashlib.sha256(report.html.encode("utf-8")).hexdigest(),
                },
                (graph_id,),
            )
            completed = run.transition(RunStatus.COMPLETED)
            emit("run.completed", "finish", {"status": completed.status.value})
            self.store.save_run(completed)
            return FlowExecutionResult(completed, tuple(events), profile, dashboard, text_dashboard, final_graph)
        except FlowCancelled:
            interrupted = run.transition(RunStatus.INTERRUPTED)
            emit("run.interrupted", "finish", {"status": interrupted.status.value})
            self.store.save_run(interrupted)
            raise
        except Exception as exc:
            emit("run.failed", "finish", {"error_type": type(exc).__name__})
            self.store.save_run(run.transition(RunStatus.FAILED))
            raise


def _demo_plan(has_documents: bool, has_proposal: bool) -> FlowPlan:
    steps = [
        FlowStep("inspect", "inspect_sources", "识别输入中的数据与文本", (), {}),
        FlowStep("profile", "profile_data", "在本地计算数据画像", ("inspect",), {}),
    ]
    prior = "profile"
    if has_documents:
        steps.append(FlowStep("extract", "extract_claims", "抽取可引用的文本主张", ("inspect",), {}))
        steps.append(FlowStep("align", "align_evidence", "交叉对齐数据指标与文本主张", ("profile", "extract"), {}))
        prior = "align"
    if has_proposal:
        steps.append(FlowStep("hypotheses", "test_hypothesis", "验证结构化业务假设", (prior,), {}))
    return FlowPlan("demo-cross-reasoning", tuple(steps), "demo")


def _run_tool(
    emit: Callable[[str, str, Mapping[str, object], tuple[str, ...]], RunEvent],
    step_id: str,
    tool_name: str,
    invoke: Callable[[], ToolResult],
) -> ToolResult:
    emit("step.started", "tools", {"step_id": step_id, "tool": tool_name}, (step_id,))
    emit("tool.started", "tools", {"step_id": step_id, "tool": tool_name}, (step_id,))
    started_at = perf_counter()
    try:
        result = invoke()
    except Exception as exc:
        duration_ms = max(0, round((perf_counter() - started_at) * 1000))
        failure = {
            "step_id": step_id,
            "tool": tool_name,
            "duration_ms": duration_ms,
            "error_type": type(exc).__name__,
        }
        emit("tool.failed", "tools", failure, (step_id,))
        emit("step.failed", "tools", failure, (step_id,))
        raise
    duration_ms = max(0, round((perf_counter() - started_at) * 1000))
    emit(
        "tool.result",
        "tools",
        {
            "step_id": step_id,
            "tool": result.tool,
            "status": result.status,
            "duration_ms": duration_ms,
            **dict(result.summary),
        },
        result.artifact_refs,
    )
    emit(
        "step.completed",
        "tools",
        {"step_id": step_id, "tool": result.tool, "status": result.status, "duration_ms": duration_ms},
        (step_id, *result.artifact_refs),
    )
    return result


def _invoke_connected_tool(
    tools: LocalAnalysisTools,
    step: FlowStep,
    data_path: Path,
    snapshot_id: str,
    document_paths: tuple[Path, ...],
    corpus_id: str,
) -> ToolResult:
    if step.tool == "inspect_sources":
        return tools.inspect_sources((data_path, *document_paths))
    if step.tool == "profile_data":
        return tools.profile_data(data_path, snapshot_id)
    if step.tool == "query_data":
        metric = step.arguments.get("metric")
        if not isinstance(metric, str) or not metric.strip():
            raise FlowPlanError("query_data requires a metric argument")
        return tools.query_data(data_path, snapshot_id, metric.strip())
    if step.tool == "extract_claims":
        return tools.extract_claims(document_paths, corpus_id)
    if step.tool == "align_evidence":
        return tools.align_evidence(data_path, snapshot_id, document_paths, corpus_id)
    if step.tool == "test_hypothesis":
        hypothesis = step.arguments.get("hypothesis")
        if not isinstance(hypothesis, Mapping):
            raise FlowPlanError("test_hypothesis requires a structured hypothesis argument")
        return tools.test_hypothesis(data_path, snapshot_id, hypothesis)
    if step.tool == "compare_periods":
        return tools.compare_periods(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            split=_optional_int(step, "split"),
        )
    if step.tool == "detect_anomalies":
        return tools.detect_anomalies(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            window=_optional_int(step, "window", 5),
            threshold=_optional_float(step, "threshold", 6.0),
        )
    if step.tool == "detect_change_points":
        return tools.detect_change_points(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            minimum_window=_optional_int(step, "minimum_window", 4),
        )
    if step.tool == "segment_rank":
        return tools.segment_rank(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            dimension=_required_text(step, "dimension"),
            split_date=_optional_text(step, "split_date"),
            minimum_samples=_optional_int(step, "minimum_samples", 1),
        )
    if step.tool == "decompose_change":
        return tools.decompose_change(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            dimension=_required_text(step, "dimension"),
            split_date=_optional_text(step, "split_date"),
            numerator_metric=_optional_text(step, "numerator_metric"),
            denominator_metric=_optional_text(step, "denominator_metric"),
        )
    if step.tool == "correlate_metrics":
        return tools.correlate_metrics(
            data_path,
            snapshot_id,
            leading_metric=_required_text(step, "leading_metric"),
            lagging_metric=_required_text(step, "lagging_metric"),
            max_lag=_optional_int(step, "max_lag", 3),
        )
    if step.tool == "compare_groups":
        return tools.compare_groups(
            data_path,
            snapshot_id,
            metric=_required_text(step, "metric"),
            dimension=_required_text(step, "dimension"),
            first_group=_required_text(step, "first_group"),
            second_group=_required_text(step, "second_group"),
            bootstrap_samples=_optional_int(step, "bootstrap_samples", 2_000),
        )
    if step.tool == "analyze_text":
        return tools.analyze_text(document_paths, corpus_id, seed=_optional_int(step, "seed", 7))
    if step.tool == "semantic_cluster":
        return tools.semantic_cluster(
            document_paths,
            corpus_id,
            model_path=_required_text(step, "model_path"),
            seed=_optional_int(step, "seed", 7),
        )
    if step.tool == "compare_topics_with_metrics":
        return tools.compare_topics_with_metrics(
            _required_text(step, "topic_ref"), _required_text(step, "metric_ref")
        )
    if step.tool == "test_text_metric_lag":
        return tools.test_text_metric_lag(
            _required_text(step, "topic_ref"),
            _required_text(step, "metric_ref"),
            max_lag=_optional_int(step, "max_lag", 3),
        )
    if step.tool == "find_explanatory_segments":
        return tools.find_explanatory_segments(
            _required_text(step, "relationship_ref"), _required_text(step, "segment_ref")
        )
    raise FlowPlanError(f"unsupported registered tool: {step.tool}")


def _required_text(step: FlowStep, name: str) -> str:
    value = step.arguments.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise FlowPlanError(f"{step.tool} requires a bounded {name} argument")
    return value.strip()


def _optional_text(step: FlowStep, name: str) -> str | None:
    value = step.arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise FlowPlanError(f"{step.tool} requires a bounded {name} argument")
    return value.strip()


def _optional_int(step: FlowStep, name: str, default: int | None = None) -> int | None:
    value = step.arguments.get(name, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FlowPlanError(f"{step.tool} requires an integer {name} argument")
    return value


def _optional_float(step: FlowStep, name: str, default: float) -> float:
    value = step.arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FlowPlanError(f"{step.tool} requires a numeric {name} argument")
    return float(value)


def _ordered_steps(steps: tuple[FlowStep, ...]) -> tuple[FlowStep, ...]:
    remaining = list(steps)
    completed: set[str] = set()
    ordered: list[FlowStep] = []
    while remaining:
        next_step = next(
            (step for step in remaining if set(step.dependencies) <= completed),
            None,
        )
        if next_step is None:
            raise FlowPlanError("flow plan must be acyclic")
        remaining.remove(next_step)
        ordered.append(next_step)
        completed.add(next_step.step_id)
    return tuple(ordered)


def parse_hypotheses(proposal: dict[str, Any] | None) -> tuple[FlowHypothesis, ...]:
    if proposal is None:
        return ()
    if not isinstance(proposal, dict) or set(proposal) != {"hypotheses"}:
        raise ValueError("agent proposal may contain only structured hypotheses")
    raw = proposal["hypotheses"]
    if not isinstance(raw, list) or len(raw) > 20:
        raise ValueError("agent proposal hypotheses must be a bounded list")
    parsed = []
    for item in raw:
        if not isinstance(item, dict) or set(item) not in (
            {"hypothesis_id", "text"},
            {"hypothesis_id", "text", "clauses"},
        ):
            raise ValueError("each hypothesis requires hypothesis_id, text, and optional structured clauses")
        node = EvidenceNode(str(item["hypothesis_id"]), "hypothesis", str(item["text"]), "pending")
        clauses = item.get("clauses")
        tool_payload = {"clauses": clauses, "source": "agent_proposed"} if clauses is not None else None
        parsed.append(FlowHypothesis(node.node_id, node.label, tool_payload))
    return tuple(parsed)


def _is_acyclic(steps: list[FlowStep]) -> bool:
    dependencies = {step.step_id: set(step.dependencies) for step in steps}
    ready = [step_id for step_id, needs in dependencies.items() if not needs]
    visited = 0
    while ready:
        completed = ready.pop()
        visited += 1
        for step_id, needs in dependencies.items():
            if completed in needs:
                needs.remove(completed)
                if not needs:
                    ready.append(step_id)
    return visited == len(steps)


def _has_forbidden_argument(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            str(key).lower() in _FORBIDDEN_ARGUMENT_KEYS or _has_forbidden_argument(item) for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_has_forbidden_argument(item) for item in value)
    return False


def _require_identifier(value: str, field: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise FlowPlanError(f"{field} must be a stable identifier")
