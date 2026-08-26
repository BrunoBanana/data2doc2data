"""Persisted deterministic policy for model-free multi-round analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
from statistics import fmean
import time
from typing import Callable

from .analysis_cycle import AnalysisCycle, AnalysisRound, EvidenceGap, RoundDecision, validate_round_decision
from .analytical_table import AnalyticalTable, load_analytical_table
from .artifacts import ArtifactStore
from .cycle_planner import PlannerWaiting
from .data_profile import profile_standard_csv
from .flow_tools import LocalAnalysisTools, REGISTERED_ANALYSIS_TOOLS, ToolResult
from .workspace import AnalysisTask
from .workspace_store import WorkspaceStore, WorkspaceStoreError


@dataclass(frozen=True)
class CycleExecutionResult:
    cycle: AnalysisCycle
    pending_artifact_refs: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class PlannerRetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 0.2
    deadline_seconds: float = 5.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_attempts, int)
            or isinstance(self.max_attempts, bool)
            or not 1 <= self.max_attempts <= 100
        ):
            raise ValueError("planner max_attempts must be an integer between 1 and 100")
        for name, value in (
            ("base_delay_seconds", self.base_delay_seconds),
            ("max_delay_seconds", self.max_delay_seconds),
            ("deadline_seconds", self.deadline_seconds),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"planner {name} must be positive")
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("planner base delay cannot exceed max delay")

    def delay(self, attempt: int) -> float:
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** max(0, attempt - 1)))


CONNECTED_CYCLE_TOOLS = frozenset(
    {
        "compare_periods",
        "detect_anomalies",
        "detect_change_points",
        "segment_rank",
        "decompose_change",
        "correlate_metrics",
        "compare_groups",
        "analyze_text",
    }
)


class ConnectedCycleRunner:
    """Let a connected planner choose each bounded tool after inspecting prior real artifacts."""

    def __init__(
        self,
        store: WorkspaceStore,
        planner,
        *,
        retry_policy: PlannerRetryPolicy | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        on_planner_event: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self.store = store
        self.planner = planner
        self.artifacts = ArtifactStore(store.path.parent / "artifacts")
        self.retry_policy = retry_policy or PlannerRetryPolicy()
        self.monotonic = monotonic
        self.sleep = sleep
        self.on_planner_event = on_planner_event

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        *,
        cycle_id: str | None = None,
    ) -> CycleExecutionResult:
        dataset = next((ref for ref in task.snapshot_refs if ref.kind == "dataset"), None)
        if dataset is None:
            raise ValueError("analysis cycle requires a dataset snapshot")
        cycle = AnalysisCycle.start(cycle_id or f"cycle-{secrets.token_hex(12)}")
        context: dict[str, object] = {
            "task_id": task.task_id,
            "snapshot_id": dataset.snapshot_id,
            "data_path": str(data_path.expanduser().resolve()),
            "document_paths": [str(path.expanduser().resolve()) for path in document_paths],
        }
        provider_resume_id: str | None = None
        self.store.save_analysis_cycle(cycle, task.task_id, context)
        tools = LocalAnalysisTools(
            (data_path.parent, *(path.parent for path in document_paths)),
            artifact_store=self.artifacts,
        )
        profile = profile_standard_csv(data_path, dataset.snapshot_id)
        projections: list[dict[str, object]] = [
            {
                "tool": "profile_data",
                "status": "completed",
                "summary": {
                    "row_count": profile.row_count,
                    "metrics": list(profile.metrics),
                    "dimensions": list(profile.dimensions),
                    "date_range": list(profile.date_range),
                    "document_count": len(document_paths),
                },
                "artifact_refs": [dataset.snapshot_id],
            }
        ]
        while cycle.can_continue:
            waiting_error: PlannerWaiting | None = None
            planned = None
            deadline = self.monotonic() + self.retry_policy.deadline_seconds
            deadline_at = _utc_deadline(self.retry_policy.deadline_seconds)
            attempts = 0
            for attempt in range(1, self.retry_policy.max_attempts + 1):
                if attempt > 1 and self.monotonic() >= deadline:
                    break
                attempts = attempt
                try:
                    planned = self.planner.decide(
                        cycle,
                        tuple(projections),
                        provider_resume_id=provider_resume_id,
                    )
                    if waiting_error is not None and self.on_planner_event is not None:
                        self.on_planner_event(
                            "planner.resumed",
                            {
                                "round_number": len(cycle.rounds) + 1,
                                "attempt": attempt,
                                "deadline_at": deadline_at,
                            },
                        )
                    break
                except PlannerWaiting as exc:
                    waiting_error = exc
                    provider_resume_id = exc.provider_resume_id or provider_resume_id
                    remaining = max(0.0, deadline - self.monotonic())
                    delay = min(self.retry_policy.delay(attempt), remaining)
                    if self.on_planner_event is not None:
                        self.on_planner_event(
                            "planner.waiting",
                            {
                                "round_number": len(cycle.rounds) + 1,
                                "attempt": attempt,
                                "retry_limit": self.retry_policy.max_attempts,
                                "backoff_ms": round(delay * 1000),
                                "deadline_at": deadline_at,
                            },
                        )
                    if attempt < self.retry_policy.max_attempts and delay > 0:
                        self.sleep(delay)
            if planned is None:
                waiting = cycle.transition("waiting_for_planner")
                self.store.save_analysis_cycle(waiting, task.task_id, context)
                deadline_exhausted = self.monotonic() >= deadline
                checkpoint_reason = (
                    "planner_deadline_exhausted" if deadline_exhausted else "planner_retry_exhausted"
                )
                self.store.save_cycle_checkpoint(
                    cycle.cycle_id,
                    provider_resume_id=provider_resume_id,
                    reason=checkpoint_reason,
                    deadline_at=deadline_at,
                )
                if self.on_planner_event is not None:
                    self.on_planner_event(
                        "cycle.checkpointed",
                        {
                            "cycle_id": cycle.cycle_id,
                            "round_number": len(cycle.rounds) + 1,
                            "attempts": attempts,
                            "resume_available": provider_resume_id is not None,
                            "reason": checkpoint_reason,
                            "deadline_at": deadline_at,
                        },
                    )
                return CycleExecutionResult(waiting, error=str(waiting_error or "planner unavailable"))
            provider_resume_id = planned.provider_resume_id
            decision = planned.decision
            prior_decision = cycle.rounds[-1].decision if cycle.rounds else None
            validate_round_decision(decision, CONNECTED_CYCLE_TOOLS, prior_decision=prior_decision)
            if not set(decision.prior_artifact_refs) <= set(cycle.artifact_refs):
                raise ValueError("planner decision references an unknown artifact")
            if decision.action == "finish":
                cycle = cycle.complete_round(AnalysisRound.completed(decision, ()))
                self.store.save_analysis_cycle(cycle, task.task_id, context)
                continue
            execution_key = _execution_key(cycle.cycle_id, decision)
            result = _execute_connected_cycle_tool(
                tools,
                decision,
                data_path,
                dataset.snapshot_id,
                document_paths,
                cycle.cycle_id,
            )
            self.store.save_cycle_execution(
                cycle.cycle_id,
                decision.round_number,
                str(decision.tool),
                execution_key,
                result.artifact_refs,
                result.agent_projection(),
            )
            projection = result.agent_projection()
            projections.append(projection)
            cycle = cycle.complete_round(AnalysisRound.completed(decision, result.artifact_refs))
            self.store.save_analysis_cycle(cycle, task.task_id, context)
        return CycleExecutionResult(cycle)


def _utc_deadline(seconds: float) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    return value.isoformat().replace("+00:00", "Z")


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
        cycle_id: str | None = None,
    ) -> CycleExecutionResult:
        dataset = next((ref for ref in task.snapshot_refs if ref.kind == "dataset"), None)
        if dataset is None:
            raise ValueError("analysis cycle requires a dataset snapshot")
        cycle = AnalysisCycle.start(cycle_id or f"cycle-{secrets.token_hex(12)}")
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
        metric = _priority_metric(table, metrics)
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
        if has_documents:
            return RoundDecision(
                round_number,
                "continue",
                "analyze_text",
                {"seed": 7},
                "数据侧结构诊断完成，补充本地文本主题、聚类与关键词证据。",
                prior_artifact_refs=previous_refs,
            )
        if table.dimensions:
            return RoundDecision(
                round_number,
                "continue",
                "segment_rank",
                {"metric": metric, "dimension": table.dimensions[0]},
                "依据前两轮结果下钻首个可审计业务维度，定位差异集中的分组。",
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


def _execute_connected_cycle_tool(
    tools: LocalAnalysisTools,
    decision: RoundDecision,
    data_path: Path,
    snapshot_id: str,
    document_paths: tuple[Path, ...],
    cycle_id: str,
) -> ToolResult:
    arguments = dict(decision.arguments)
    tool = decision.tool
    if tool == "compare_periods":
        return tools.compare_periods(data_path, snapshot_id, metric=_required(arguments, "metric"), split=arguments.get("split"))
    if tool == "detect_anomalies":
        return tools.detect_anomalies(
            data_path,
            snapshot_id,
            metric=_required(arguments, "metric"),
            window=int(arguments.get("window", 5)),
            threshold=float(arguments.get("threshold", 6.0)),
        )
    if tool == "detect_change_points":
        return tools.detect_change_points(
            data_path,
            snapshot_id,
            metric=_required(arguments, "metric"),
            minimum_window=int(arguments.get("minimum_window", 4)),
        )
    if tool == "segment_rank":
        return tools.segment_rank(
            data_path,
            snapshot_id,
            metric=_required(arguments, "metric"),
            dimension=_required(arguments, "dimension"),
            split_date=_optional_text(arguments.get("split_date")),
            minimum_samples=int(arguments.get("minimum_samples", 1)),
        )
    if tool == "decompose_change":
        return tools.decompose_change(
            data_path,
            snapshot_id,
            metric=_required(arguments, "metric"),
            dimension=_required(arguments, "dimension"),
            split_date=_optional_text(arguments.get("split_date")),
            numerator_metric=_optional_text(arguments.get("numerator_metric")),
            denominator_metric=_optional_text(arguments.get("denominator_metric")),
        )
    if tool == "correlate_metrics":
        return tools.correlate_metrics(
            data_path,
            snapshot_id,
            leading_metric=_required(arguments, "leading_metric"),
            lagging_metric=_required(arguments, "lagging_metric"),
            max_lag=int(arguments.get("max_lag", 3)),
        )
    if tool == "compare_groups":
        return tools.compare_groups(
            data_path,
            snapshot_id,
            metric=_required(arguments, "metric"),
            dimension=_required(arguments, "dimension"),
            first_group=_required(arguments, "first_group"),
            second_group=_required(arguments, "second_group"),
            bootstrap_samples=int(arguments.get("bootstrap_samples", 2_000)),
        )
    if tool == "analyze_text":
        return tools.analyze_text(document_paths, f"corpus-{cycle_id}", seed=int(arguments.get("seed", 7)))
    raise ValueError(f"unsupported connected cycle tool: {tool}")


def _required(arguments: dict[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _priority_metric(table: AnalyticalTable, metrics: tuple[str, ...]) -> str:
    """Choose the metric with the strongest normalized two-window shift."""
    ranked: list[tuple[float, int, str]] = []
    for position, metric in enumerate(metrics):
        values = [row.value for row in sorted(table.rows, key=lambda row: row.date) if row.metric == metric]
        split = len(values) // 2
        if split < 1 or split >= len(values):
            ranked.append((0.0, -position, metric))
            continue
        baseline = fmean(values[:split])
        current = fmean(values[split:])
        scale = max(abs(baseline), abs(current), 1e-12)
        ranked.append((abs(current - baseline) / scale, -position, metric))
    return max(ranked)[2]
