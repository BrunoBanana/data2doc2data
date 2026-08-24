"""Persisted deterministic policy for model-free multi-round analysis."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import secrets

from .analysis_cycle import AnalysisCycle, AnalysisRound, EvidenceGap, RoundDecision, validate_round_decision
from .analytical_table import AnalyticalTable, load_analytical_table
from .artifacts import ArtifactStore
from .flow_tools import LocalAnalysisTools, REGISTERED_ANALYSIS_TOOLS, ToolResult
from .workspace import AnalysisTask
from .workspace_store import WorkspaceStore, WorkspaceStoreError


@dataclass(frozen=True)
class CycleExecutionResult:
    cycle: AnalysisCycle
    pending_artifact_refs: tuple[str, ...] = ()
    error: str | None = None


class DemoCycleRunner:
    """Choose each local round from source schema and the previous real artifact."""

    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self.artifacts = ArtifactStore(store.path.parent / "artifacts")

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        *,
        interrupt_after_tool_round: int | None = None,
    ) -> CycleExecutionResult:
        dataset = next((ref for ref in task.snapshot_refs if ref.kind == "dataset"), None)
        if dataset is None:
            raise ValueError("analysis cycle requires a dataset snapshot")
        cycle = AnalysisCycle.start(f"cycle-{secrets.token_hex(12)}")
        context = {
            "task_id": task.task_id,
            "snapshot_id": dataset.snapshot_id,
            "data_path": str(data_path.expanduser().resolve()),
            "document_paths": [str(path.expanduser().resolve()) for path in document_paths],
        }
        self.store.save_analysis_cycle(cycle, task.task_id, context)
        return self._drive(cycle, task, context, interrupt_after_tool_round=interrupt_after_tool_round)

    def resume(self, cycle_id: str) -> CycleExecutionResult:
        cycle = self.store.get_analysis_cycle(cycle_id)
        if cycle is None:
            raise WorkspaceStoreError("analysis cycle does not exist")
        context = self.store.get_analysis_cycle_context(cycle_id)
        task = self.store.get_task(str(context.get("task_id", "")))
        if task is None:
            raise WorkspaceStoreError("analysis cycle task does not exist")
        if cycle.status == "completed":
            return CycleExecutionResult(cycle)
        if cycle.status not in {"interrupted", "waiting_for_planner", "running"}:
            raise WorkspaceStoreError("analysis cycle cannot be resumed")
        cycle = cycle.transition("running")
        self.store.save_analysis_cycle(cycle, task.task_id, context)
        return self._drive(cycle, task, context)

    def _drive(
        self,
        cycle: AnalysisCycle,
        task: AnalysisTask,
        context: dict[str, object],
        *,
        interrupt_after_tool_round: int | None = None,
    ) -> CycleExecutionResult:
        data_path = Path(str(context["data_path"]))
        document_paths = tuple(Path(str(path)) for path in context.get("document_paths", []))
        snapshot_id = str(context["snapshot_id"])
        table = load_analytical_table(data_path, snapshot_id)
        tools = LocalAnalysisTools(
            (data_path.parent, *(path.parent for path in document_paths)),
            artifact_store=self.artifacts,
        )
        while cycle.can_continue:
            decision = self._decide(cycle, table, bool(document_paths))
            prior_decision = cycle.rounds[-1].decision if cycle.rounds else None
            validate_round_decision(decision, REGISTERED_ANALYSIS_TOOLS, prior_decision=prior_decision)
            if decision.action == "finish":
                cycle = cycle.complete_round(AnalysisRound.completed(decision, ()))
                self.store.save_analysis_cycle(cycle, task.task_id, context)
                continue
            execution_key = _execution_key(cycle.cycle_id, decision)
            existing = self.store.get_cycle_execution(cycle.cycle_id, decision.round_number)
            if existing is not None:
                if existing["execution_key"] != execution_key:
                    raise WorkspaceStoreError("checkpoint decision does not match persisted execution")
                artifact_refs = tuple(str(ref) for ref in existing["artifact_refs"])
            else:
                try:
                    result = self._execute(tools, decision, data_path, snapshot_id, document_paths, cycle.cycle_id)
                except Exception as exc:
                    failed = cycle.transition("failed")
                    self.store.save_analysis_cycle(failed, task.task_id, context)
                    return CycleExecutionResult(failed, error=f"{type(exc).__name__}: {exc}")
                artifact_refs = result.artifact_refs
                self.store.save_cycle_execution(
                    cycle.cycle_id,
                    decision.round_number,
                    str(decision.tool),
                    execution_key,
                    artifact_refs,
                    result.agent_projection(),
                )
            if interrupt_after_tool_round == decision.round_number:
                interrupted = cycle.transition("interrupted")
                self.store.save_analysis_cycle(interrupted, task.task_id, context)
                return CycleExecutionResult(interrupted, artifact_refs)
            cycle = cycle.complete_round(AnalysisRound.completed(decision, artifact_refs))
            self.store.save_analysis_cycle(cycle, task.task_id, context)
        return CycleExecutionResult(cycle)

    def _decide(self, cycle: AnalysisCycle, table: AnalyticalTable, has_documents: bool) -> RoundDecision:
        round_number = len(cycle.rounds) + 1
        metrics = tuple(dict.fromkeys(row.metric for row in table.rows))
        metric = metrics[0]
        previous_refs = cycle.rounds[-1].artifact_refs if cycle.rounds else ()
        if round_number == 1:
            count = sum(row.metric == metric for row in table.rows)
            window = 5 if count > 6 else 3
            return RoundDecision(
                1,
                "continue",
                "detect_anomalies",
                {"metric": metric, "window": window, "threshold": 4.0},
                "先用稳健局部基线识别需要解释的异常点。",
                evidence_gaps=(EvidenceGap("gap-structure", "尚未判断异常是否伴随持续结构变化。", "detect_change_points"),),
            )
        if round_number == 2:
            previous = self.artifacts.load(previous_refs[0]) if previous_refs else {}
            payload = previous.get("payload", {}) if isinstance(previous, dict) else {}
            observations = payload.get("observations", {}) if isinstance(payload, dict) else {}
            anomaly_count = observations.get("anomaly_count", 0) if isinstance(observations, dict) else 0
            if isinstance(anomaly_count, int) and anomaly_count > 0:
                tool = "detect_change_points"
                arguments = {"metric": metric, "minimum_window": 3}
                rationale = "上一轮发现异常点，继续检验其附近是否存在持续水平变化。"
            else:
                tool = "compare_periods"
                arguments = {"metric": metric}
                rationale = "上一轮未发现明显异常，改用前后窗口比较确认整体变化。"
            return RoundDecision(2, "continue", tool, arguments, rationale, prior_artifact_refs=previous_refs)
        if table.dimensions:
            return RoundDecision(
                round_number,
                "continue",
                "segment_rank",
                {"metric": metric, "dimension": table.dimensions[0]},
                "依据前两轮结果下钻首个可审计业务维度，定位差异集中的分组。",
                prior_artifact_refs=previous_refs,
            )
        if has_documents:
            return RoundDecision(
                round_number,
                "continue",
                "analyze_text",
                {"seed": 7},
                "数据侧结构诊断完成，补充本地文本主题与聚类证据。",
                prior_artifact_refs=previous_refs,
            )
        return RoundDecision(
            round_number,
            "finish",
            None,
            {},
            "当前输入没有更多可审计维度或文本材料，停止扩展。",
            prior_artifact_refs=previous_refs,
            stop_reason="no_valid_revision",
        )

    @staticmethod
    def _execute(
        tools: LocalAnalysisTools,
        decision: RoundDecision,
        data_path: Path,
        snapshot_id: str,
        document_paths: tuple[Path, ...],
        cycle_id: str,
    ) -> ToolResult:
        arguments = dict(decision.arguments)
        if decision.tool == "detect_anomalies":
            return tools.detect_anomalies(data_path, snapshot_id, **arguments)
        if decision.tool == "detect_change_points":
            return tools.detect_change_points(data_path, snapshot_id, **arguments)
        if decision.tool == "compare_periods":
            return tools.compare_periods(data_path, snapshot_id, **arguments)
        if decision.tool == "segment_rank":
            return tools.segment_rank(data_path, snapshot_id, **arguments)
        if decision.tool == "analyze_text":
            return tools.analyze_text(document_paths, f"corpus-{cycle_id}", **arguments)
        raise ValueError(f"unsupported demo cycle tool: {decision.tool}")


def _execution_key(cycle_id: str, decision: RoundDecision) -> str:
    encoded = json.dumps(
        {"cycle_id": cycle_id, "decision": decision.to_dict()},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
