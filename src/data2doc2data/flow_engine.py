"""Bounded dual-runner execution for observable data and text reasoning flows."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import secrets
from typing import Any

from .data_profile import DataProfile, build_default_dashboard, profile_standard_csv
from .dashboard import DashboardSpec
from .documents import build_document_corpus
from .evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceNode
from .flow_tools import LocalAnalysisTools, ToolResult
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

    REGISTERED_TOOLS = frozenset(
        {"inspect_sources", "profile_data", "query_data", "extract_claims", "align_evidence", "test_hypothesis"}
    )

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

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
    ) -> FlowExecutionResult:
        run = AnalysisRun.create(f"run-{secrets.token_hex(12)}", task.task_id, task.snapshot_refs).transition(
            RunStatus.RUNNING
        )
        events: list[RunEvent] = []
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []
        graph_id = f"graph-{run.run_id}"

        def emit(kind: str, phase: str, summary: Mapping[str, object], refs: tuple[str, ...] = ()) -> RunEvent:
            event = RunEvent.create(run.run_id, len(events) + 1, kind, phase, summary, refs)
            if events:
                self.store.append_event(event)
            else:
                self.store.create_run(run, event)
            events.append(event)
            if on_event is not None:
                on_event(event)
            return event

        def graph() -> EvidenceGraph:
            return EvidenceGraph(graph_id, tuple(nodes), tuple(edges))

        def add_node(node: EvidenceNode, phase: str) -> None:
            nodes.append(node)
            current = graph()
            self.store.save_run_artifact(run.run_id, "evidence_graph", current.to_dict())
            emit(
                "node.added",
                phase,
                {"node_id": node.node_id, "node_kind": node.kind, "status": node.status, "label": node.label},
                tuple(ref for ref in (node.node_id, node.artifact_ref) if ref),
            )

        def add_edge(edge: EvidenceEdge, phase: str) -> None:
            edges.append(edge)
            current = graph()
            self.store.save_run_artifact(run.run_id, "evidence_graph", current.to_dict())
            summary = {
                "edge_id": edge.edge_id,
                "source": edge.source,
                "target": edge.target,
                "relationship": edge.relationship,
            }
            emit("edge.added", phase, summary, (edge.edge_id,))
            emit("edge.activated", phase, summary, (edge.edge_id,))

        def check_cancelled() -> None:
            if cancelled is not None and cancelled():
                raise FlowPlanError("analysis run was cancelled")

        emit("run.started", "setup", {"snapshot_count": len(run.snapshot_refs), "runner": plan.runner})
        try:
            dataset = next((ref for ref in run.snapshot_refs if ref.kind == "dataset"), None)
            if dataset is None:
                raise ValueError("analysis run requires a dataset snapshot")
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

            tools = LocalAnalysisTools((data_path.parent, *(path.parent for path in document_paths)))
            if plan.runner == "connected":
                for step in _ordered_steps(plan.steps):
                    check_cancelled()
                    _emit_tool(
                        emit,
                        step.step_id,
                        _invoke_connected_tool(
                            tools,
                            step,
                            data_path,
                            dataset.snapshot_id,
                            document_paths,
                            f"corpus-{run.run_id}",
                        ),
                    )
            else:
                check_cancelled()
                _emit_tool(emit, "inspect", tools.inspect_sources((data_path, *document_paths)))

            check_cancelled()
            emit(
                "compute.plan.created",
                "compute",
                {"operation": "profile and aggregate", "fields": ["date", "metric", "value"], "row_limit": 1000},
            )
            profile_result = tools.profile_data(data_path, dataset.snapshot_id)
            if plan.runner == "demo":
                _emit_tool(emit, "profile", profile_result)
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

            check_cancelled()
            corpus = build_document_corpus(document_paths, f"corpus-{run.run_id}")
            text_dashboard = build_text_dashboard(corpus)
            if document_paths and plan.runner == "demo":
                _emit_tool(emit, "extract", tools.extract_claims(document_paths, corpus.corpus_id))
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
                _emit_tool(
                    emit,
                    "align",
                    tools.align_evidence(data_path, dataset.snapshot_id, document_paths, corpus.corpus_id),
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

            for index, (hypothesis_id, hypothesis_text) in enumerate(hypotheses):
                emit(
                    "hypothesis.created",
                    "hypotheses",
                    {"hypothesis_id": hypothesis_id, "status": "pending"},
                    (hypothesis_id,),
                )
                add_node(EvidenceNode(hypothesis_id, "hypothesis", hypothesis_text, "pending"), "hypotheses")
                validation_id = f"validation-{index + 1}"
                add_node(EvidenceNode(validation_id, "validation", "当前证据不足", "insufficient"), "validation")
                add_edge(
                    EvidenceEdge(f"edge-hypothesis-{index + 1}", validation_id, hypothesis_id, "tests"), "validation"
                )
                add_edge(
                    EvidenceEdge(f"edge-insufficient-{index + 1}", "data-signal", validation_id, "insufficient_for"),
                    "validation",
                )
                emit(
                    "validation.completed",
                    "validation",
                    {"hypothesis_id": hypothesis_id, "status": "insufficient"},
                    (hypothesis_id,),
                )

            final_graph = graph()
            emit("evidence.linked", "evidence", {"node_count": len(nodes), "edge_count": len(edges)}, (graph_id,))
            report = build_html_report(
                task,
                dashboard.to_dict(),
                text_dashboard.to_dict(),
                final_graph.to_dict(),
                run_count=len(self.store.list_runs(task.task_id)),
            )
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


def _emit_tool(
    emit: Callable[[str, str, Mapping[str, object], tuple[str, ...]], RunEvent],
    step_id: str,
    result: ToolResult,
) -> None:
    emit("tool.started", "tools", {"step_id": step_id, "tool": result.tool}, (step_id,))
    emit(
        "tool.result",
        "tools",
        {"step_id": step_id, "tool": result.tool, "status": result.status, **dict(result.summary)},
        result.artifact_refs,
    )


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
    raise FlowPlanError(f"unsupported registered tool: {step.tool}")


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


def parse_hypotheses(proposal: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
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
