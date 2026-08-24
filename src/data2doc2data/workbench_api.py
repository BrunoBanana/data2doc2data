"""Application service for authenticated workbench task APIs."""

from __future__ import annotations

from http import HTTPStatus
import hashlib
import json
from pathlib import Path
import secrets
import re
import threading
from typing import Any, Mapping

from .analysis_cycle import AnalysisCycle, CyclePlanError
from .cycle_planner import ConnectedCyclePlanner, PlannerWaiting
from .run_events import RunEvent, RunEventError
from .data_profile import DataProfileError, build_default_dashboard, profile_standard_csv
from .documents import build_document_corpus
from .flagship_cases import FlagshipCaseCatalog, FlagshipCaseError
from .flow_engine import ConnectedFlowRunner, DemoFlowRunner, FlowCancelled
from .orchestrator import AnalysisOrchestrator
from .reporting import HtmlReportArtifact, build_html_report
from .text_dashboard import build_text_dashboard
from .workspace import AnalysisRun, AnalysisTask, RunStatus, SnapshotRef, WorkspaceContractError, _utc_now
from .workspace_store import WorkspaceStore, WorkspaceStoreError


class WorkbenchApiError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class WorkbenchService:
    def __init__(self, store: WorkspaceStore, gateway=None, agent_workspace: Path | None = None) -> None:
        self.store = store
        self.gateway = gateway
        self.agent_workspace = (agent_workspace or Path.cwd()).expanduser().resolve()
        self.flagship_cases = FlagshipCaseCatalog.load()
        self._retry_lock = threading.Lock()
        self._run_lock = threading.Lock()
        self._run_controls: dict[str, threading.Event] = {}
        self._run_threads: dict[str, threading.Thread] = {}

    def list_flagship_cases(self) -> dict[str, object]:
        return {"cases": [case.to_summary_dict() for case in self.flagship_cases.list()]}

    def load_flagship_case(self, owner_id: str, case_id: str, payload: object | None = None) -> dict[str, object]:
        try:
            body = _body(payload or {})
            analysis_mode = body.get("analysis_mode", "demo")
            agent_provider = body.get("agent_provider")
            _analysis_journey(analysis_mode, agent_provider)
            package = self.flagship_cases.package(case_id)
            created = self.create_task(
                owner_id,
                {
                    "title": package.case.title,
                    "goal": package.case.business_question,
                    "analysis_mode": analysis_mode,
                    "agent_provider": agent_provider,
                },
            )["task"]
            task = AnalysisTask.from_dict(created)
            dataset_digest = _file_digest(package.metrics_path)
            if dataset_digest is None:
                raise FlagshipCaseError("flagship case dataset is unavailable")
            dataset_ref = SnapshotRef("dataset", f"dataset-{dataset_digest[:24]}", dataset_digest)
            self.store.register_snapshot(dataset_ref, package.metrics_path)
            attached = self.attach_assets(
                owner_id,
                task.task_id,
                {"snapshot_refs": [dataset_ref.to_dict()]},
            )["task"]
            imported = self.import_documents(
                owner_id,
                task.task_id,
                {"paths": [str(path) for path in package.document_paths]},
            )
            artifact = {
                "case": package.case.to_summary_dict(),
                "rules": json.loads(package.rules_path.read_text(encoding="utf-8")),
                "hypotheses": json.loads(package.hypotheses_path.read_text(encoding="utf-8")),
                "expected": json.loads(package.expected_path.read_text(encoding="utf-8")),
                "demo_flow": json.loads(package.demo_flow_path.read_text(encoding="utf-8")),
                "journey": analysis_mode,
            }
            self.store.save_task_artifact(task.task_id, "flagship_case", artifact)
            dashboard = self.task_dashboard(owner_id, task.task_id)
        except (FlagshipCaseError, WorkspaceContractError, WorkspaceStoreError, OSError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"task": imported.get("task", attached), "dashboard": dashboard, "case": artifact["case"]}

    def list_tasks(self, owner_id: str) -> dict[str, object]:
        return {"tasks": [task.to_dict() for task in self.store.list_tasks_for_owner(owner_id)]}

    def get_task(self, owner_id: str, task_id: str) -> dict[str, object]:
        return {"task": self._owned_task(owner_id, task_id).to_dict()}

    def agent_context(self, owner_id: str, task_id: str) -> str:
        """Return bounded task metadata for an agent prompt, never local paths or raw rows."""
        task = self._owned_task(owner_id, task_id)
        assets = ", ".join(f"{ref.kind}:{ref.snapshot_id}" for ref in task.snapshot_refs[:50]) or "无"
        return (
            "WORKBENCH TASK CONTEXT\n"
            f"任务: {task.title}\n"
            f"目标: {task.goal}\n"
            f"状态: {task.status.value}\n"
            f"锁定资产: {len(task.snapshot_refs)}\n"
            f"资产标识: {assets}\n"
            "边界: 原始数据保留在本机；仅使用服务端提供的统计、证据摘要和锁定资产标识。"
        )[:4_000]

    def create_task(self, owner_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        try:
            analysis_mode = body.get("analysis_mode", "demo")
            agent_provider = body.get("agent_provider")
            _analysis_journey(analysis_mode, agent_provider)
            task = AnalysisTask.create(
                task_id=f"task-{secrets.token_hex(12)}",
                title=body.get("title", ""),
                goal=body.get("goal", ""),
                analysis_mode=analysis_mode,
                agent_provider=agent_provider,
            )
            self.store.save_task(task)
            self.store.assign_task_owner(task.task_id, owner_id)
        except (WorkspaceContractError, WorkspaceStoreError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"task": task.to_dict()}

    def update_task(self, owner_id: str, task_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        current = self._owned_task(owner_id, task_id)
        try:
            updated = AnalysisTask(
                task_id=current.task_id,
                title=body.get("title", current.title),
                goal=body.get("goal", current.goal),
                status=current.status,
                snapshot_refs=current.snapshot_refs,
                created_at=current.created_at,
                updated_at=_utc_now(),
                analysis_mode=current.analysis_mode,
                agent_provider=current.agent_provider,
            )
            self.store.save_task(updated)
        except (WorkspaceContractError, WorkspaceStoreError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"task": updated.to_dict()}

    def attach_assets(self, owner_id: str, task_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        raw_refs = body.get("snapshot_refs")
        if not isinstance(raw_refs, list):
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "snapshot_refs must be a list")
        current = self._owned_task(owner_id, task_id)
        try:
            supplied = tuple(SnapshotRef.from_dict(item) for item in raw_refs if isinstance(item, Mapping))
            if len(supplied) != len(raw_refs):
                raise WorkspaceContractError("snapshot_refs must contain objects")
            refs = {(ref.kind, ref.snapshot_id): ref for ref in current.snapshot_refs}
            refs.update({(ref.kind, ref.snapshot_id): ref for ref in supplied})
            updated = AnalysisTask(
                task_id=current.task_id,
                title=current.title,
                goal=current.goal,
                status=current.status,
                snapshot_refs=tuple(refs.values()),
                created_at=current.created_at,
                updated_at=_utc_now(),
                analysis_mode=current.analysis_mode,
                agent_provider=current.agent_provider,
            )
            self.store.save_task(updated)
        except (WorkspaceContractError, WorkspaceStoreError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"task": updated.to_dict()}

    def start_run(self, owner_id: str, task_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        task = self._owned_task(owner_id, task_id)
        if body.get("execute") is True and body.get("stream") is True:
            return self._start_streamed_run(task, body)
        if body.get("execute") is True:
            data_path, document_paths = self._execution_inputs(task)
            try:
                proposal = self._proposal_with_case_hypotheses(task.task_id, body.get("proposal"))
                if task.analysis_mode == "connected":
                    if "flow_plan" in body:
                        raise WorkbenchApiError(
                            HTTPStatus.UNPROCESSABLE_ENTITY,
                            "browser-authored flow_plan is no longer accepted; the backend planner owns connected runs",
                        )
                    flow_plan = self._backend_connected_flow_plan(task, data_path, document_paths)
                    result = ConnectedFlowRunner(self.store).run(task, data_path, document_paths, flow_plan, proposal)
                else:
                    result = AnalysisOrchestrator(self.store).run(task, data_path, document_paths, proposal)
                graph = result.evidence_graph.to_dict()
                self.store.save_run_artifact(result.run.run_id, "evidence_graph", graph)
            except (ValueError, WorkspaceStoreError) as exc:
                raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
            return {
                "run": result.run.to_dict(),
                "events": [event.to_dict() for event in result.events],
                "evidence_graph": graph,
                "artifact_dashboard": self.store.get_run_artifact(result.run.run_id, "artifact_dashboard"),
            }
        try:
            run = AnalysisRun.create(
                run_id=f"run-{secrets.token_hex(12)}",
                task_id=task.task_id,
                snapshot_refs=task.snapshot_refs,
            ).transition(RunStatus.RUNNING)
            event = RunEvent.create(run.run_id, 1, "run.started", "setup", {"snapshot_count": len(run.snapshot_refs)})
            self.store.create_run(run, event)
        except (WorkspaceContractError, WorkspaceStoreError, RunEventError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"run": run.to_dict()}

    def cancel_run(self, owner_id: str, run_id: str) -> dict[str, object]:
        if not self.store.owner_can_access_run(run_id, owner_id):
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        run = self.store.get_run(run_id)
        if run is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        with self._run_lock:
            control = self._run_controls.get(run_id)
            if control is not None:
                control.set()
        return {"accepted": control is not None, "run": run.to_dict()}

    def run_graph(self, owner_id: str, run_id: str) -> dict[str, object]:
        if not self.store.owner_can_access_run(run_id, owner_id):
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        graph = self.store.get_run_artifact(run_id, "evidence_graph")
        if graph is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "evidence graph not found")
        return {"evidence_graph": graph}

    def list_runs(self, owner_id: str, task_id: str) -> dict[str, object]:
        task = self._owned_task(owner_id, task_id)
        items = []
        for run in self.store.list_runs(task_id):
            events = self.store.events_after(run.run_id)
            failed = next((event for event in reversed(events) if event.kind == "run.failed"), None)
            item = run.to_dict()
            item.update(
                {
                    "stale": run.snapshot_refs != task.snapshot_refs,
                    "event_count": len(events),
                    "failure_type": failed.summary.get("error_type") if failed else None,
                }
            )
            items.append(item)
        return {"runs": items}

    def run_detail(self, owner_id: str, run_id: str) -> dict[str, object]:
        if not self.store.owner_can_access_run(run_id, owner_id):
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        run = self.store.get_run(run_id)
        if run is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        graph = self.store.get_run_artifact(run_id, "evidence_graph")
        artifact_dashboard = self.store.get_run_artifact(run_id, "artifact_dashboard")
        return {
            "run": run.to_dict(),
            "events": [event.to_dict() for event in self.store.events_after(run_id)],
            "evidence_graph": graph,
            "artifact_dashboard": artifact_dashboard,
        }

    def retry_run(self, owner_id: str, run_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        key = body.get("idempotency_key")
        if not isinstance(key, str) or re.fullmatch(r"[A-Za-z0-9._:-]{8,120}", key) is None:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "idempotency_key is invalid")
        if not self.store.owner_can_access_run(run_id, owner_id):
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        previous = self.store.get_run(run_id)
        if previous is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        scope = f"retry:{run_id}"
        with self._retry_lock:
            cached = self.store.get_idempotent_response(owner_id, scope, key)
            if isinstance(cached, dict):
                return {**cached, "replayed": True}
            result = self.start_run(owner_id, previous.task_id, {"execute": True})
            response = {**result, "retried_from": run_id, "replayed": False}
            self.store.save_idempotent_response(owner_id, scope, key, response)
            return response

    def import_documents(self, owner_id: str, task_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        raw_paths = body.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths or any(not isinstance(item, str) for item in raw_paths):
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "paths must be a non-empty list of strings")
        paths = tuple(Path(item).expanduser() for item in raw_paths)
        if any(not path.is_absolute() for path in paths):
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "document paths must be absolute")
        corpus = build_document_corpus(paths, f"corpus-{task_id}")
        refs: list[SnapshotRef] = []
        for document in corpus.documents:
            source = next((path for path in paths if _file_digest(path) == document.sha256), None)
            if source is None:
                continue
            ref = SnapshotRef("document", f"document-{document.sha256[:24]}", document.sha256)
            self.store.register_snapshot(ref, source)
            refs.append(ref)
        updated = self.attach_assets(owner_id, task_id, {"snapshot_refs": [ref.to_dict() for ref in refs]})["task"]
        updated_task = AnalysisTask.from_dict(updated)
        successful_digests = {document.sha256 for document in corpus.documents}
        failed_paths = [path for path in paths if _file_digest(path) not in successful_digests]
        registered_paths = [
            registered
            for ref in updated_task.snapshot_refs
            if ref.kind == "document"
            for registered in (self.store.snapshot_path(ref),)
            if registered is not None
        ]
        combined_paths = tuple(dict.fromkeys([*registered_paths, *failed_paths]))
        text_dashboard = build_text_dashboard(build_document_corpus(combined_paths, f"corpus-{task_id}")).to_dict()
        document_refs = [ref.to_dict() for ref in updated_task.snapshot_refs if ref.kind == "document"]
        self.store.save_task_artifact(
            task_id,
            "text_dashboard",
            {"document_snapshot_refs": document_refs, "dashboard": text_dashboard},
        )
        return {
            "task": updated,
            "text_dashboard": text_dashboard,
        }

    def task_dashboard(self, owner_id: str, task_id: str) -> dict[str, object]:
        task = self._owned_task(owner_id, task_id)
        return self._task_dashboard(task)

    def _task_dashboard(self, task: AnalysisTask) -> dict[str, object]:
        dataset_refs = [ref for ref in task.snapshot_refs if ref.kind == "dataset"]
        dashboard = None
        if dataset_refs:
            ref = dataset_refs[-1]
            path = self.store.snapshot_path(ref)
            if path is None:
                raise WorkbenchApiError(HTTPStatus.CONFLICT, "dataset snapshot is not available locally")
            try:
                profile = profile_standard_csv(path, ref.snapshot_id)
            except DataProfileError as exc:
                raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
            if profile.sha256 != ref.sha256:
                raise WorkbenchApiError(HTTPStatus.CONFLICT, "dataset snapshot content has changed")
            dashboard = build_default_dashboard(profile).to_dict()
        document_paths_list: list[Path] = []
        for ref in task.snapshot_refs:
            if ref.kind != "document":
                continue
            path = self.store.snapshot_path(ref)
            if path is None:
                raise WorkbenchApiError(HTTPStatus.CONFLICT, "document snapshot is not available locally")
            if _file_digest(path) != ref.sha256:
                raise WorkbenchApiError(HTTPStatus.CONFLICT, "document snapshot content has changed")
            document_paths_list.append(path)
        document_paths = tuple(document_paths_list)
        text_dashboard = None
        document_refs = [ref.to_dict() for ref in task.snapshot_refs if ref.kind == "document"]
        artifact = self.store.get_task_artifact(task.task_id, "text_dashboard")
        if (
            isinstance(artifact, Mapping)
            and artifact.get("document_snapshot_refs") == document_refs
            and isinstance(artifact.get("dashboard"), Mapping)
        ):
            text_dashboard = dict(artifact["dashboard"])
        elif document_paths:
            corpus = build_document_corpus(document_paths, f"corpus-{task.task_id}")
            text_dashboard = build_text_dashboard(corpus).to_dict()
        return {"dashboard": dashboard, "text_dashboard": text_dashboard}

    def task_report(self, owner_id: str, task_id: str) -> HtmlReportArtifact:
        task = self._owned_task(owner_id, task_id)
        return self._task_report(task)

    def local_task_report(self, task_id: str) -> HtmlReportArtifact:
        """Generate a report for a local CLI/MCP caller with direct workspace access."""
        task = self.store.get_task(task_id)
        if task is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "task not found")
        return self._task_report(task)

    def _task_report(self, task: AnalysisTask) -> HtmlReportArtifact:
        combined = self._task_dashboard(task)
        runs = self.store.list_runs(task.task_id)
        graph = None
        artifact_dashboard = None
        for run in runs:
            candidate = self.store.get_run_artifact(run.run_id, "evidence_graph")
            if isinstance(candidate, Mapping):
                graph = candidate
                diagnostic_candidate = self.store.get_run_artifact(run.run_id, "artifact_dashboard")
                if isinstance(diagnostic_candidate, Mapping):
                    artifact_dashboard = diagnostic_candidate
                break
        return build_html_report(
            task,
            combined.get("dashboard") if isinstance(combined.get("dashboard"), Mapping) else None,
            combined.get("text_dashboard") if isinstance(combined.get("text_dashboard"), Mapping) else None,
            graph if isinstance(graph, Mapping) else None,
            run_count=len(runs),
            artifact_dashboard=artifact_dashboard,
        )

    def events_after(self, owner_id: str, run_id: str, after: object, limit: object) -> dict[str, object]:
        if not self.store.owner_can_access_run(run_id, owner_id):
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "run not found")
        try:
            sequence = int(after)
            maximum = int(limit)
            events = self.store.events_after(run_id, sequence, maximum)
        except (TypeError, ValueError, WorkspaceStoreError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"events": [event.to_dict() for event in events]}

    def _backend_connected_flow_plan(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
    ) -> dict[str, object]:
        if self.gateway is None or not task.agent_provider:
            raise WorkbenchApiError(HTTPStatus.SERVICE_UNAVAILABLE, "connected backend planner is unavailable")
        dataset = next((ref for ref in task.snapshot_refs if ref.kind == "dataset"), None)
        if dataset is None:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "connected analysis requires a dataset")
        profile = profile_standard_csv(data_path, dataset.snapshot_id)
        projection = {
            "tool": "profile_data",
            "status": "completed",
            "summary": {
                "task_title": task.title,
                "task_goal": task.goal,
                "row_count": profile.row_count,
                "metrics": list(profile.metrics),
                "dimensions": list(profile.dimensions),
                "date_range": list(profile.date_range),
                "document_count": len(document_paths),
            },
            "artifact_refs": [dataset.snapshot_id],
        }
        cycle = AnalysisCycle.start(f"cycle-plan-{secrets.token_hex(8)}")
        planner = ConnectedCyclePlanner(
            self.gateway,
            task.agent_provider,
            self.agent_workspace,
            ConnectedFlowRunner.REGISTERED_TOOLS,
        )
        try:
            planned = planner.decide(cycle, (projection,))
        except PlannerWaiting as exc:
            raise WorkbenchApiError(HTTPStatus.SERVICE_UNAVAILABLE, str(exc)) from exc
        except CyclePlanError as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, f"invalid backend planner decision: {exc}") from exc
        steps: list[dict[str, object]] = [
            {
                "step_id": "inspect",
                "tool": "inspect_sources",
                "purpose": "识别本地输入模态与质量诊断",
                "dependencies": [],
                "arguments": {},
            },
            {
                "step_id": "profile",
                "tool": "profile_data",
                "purpose": "在本地计算数据画像",
                "dependencies": ["inspect"],
                "arguments": {},
            },
        ]
        terminal_dependencies = ["profile"]
        if document_paths:
            steps.extend(
                [
                    {
                        "step_id": "extract",
                        "tool": "extract_claims",
                        "purpose": "在本地抽取带引用的文本主张",
                        "dependencies": ["inspect"],
                        "arguments": {},
                    },
                    {
                        "step_id": "align",
                        "tool": "align_evidence",
                        "purpose": "对齐数据指标与文本主张",
                        "dependencies": ["profile", "extract"],
                        "arguments": {},
                    },
                ]
            )
            terminal_dependencies = ["align"]
        decision = planned.decision
        existing_tools = {str(step["tool"]) for step in steps}
        if decision.action == "continue" and decision.tool not in existing_tools:
            steps.append(
                {
                    "step_id": "agent-round-1",
                    "tool": decision.tool,
                    "purpose": decision.rationale_summary,
                    "dependencies": terminal_dependencies,
                    "arguments": dict(decision.arguments),
                }
            )
        return {"plan_id": f"backend-{cycle.cycle_id}", "steps": steps}

    def _start_streamed_run(
        self,
        task: AnalysisTask,
        body: Mapping[str, object],
    ) -> dict[str, object]:
        data_path, document_paths = self._execution_inputs(task)
        proposal = self._proposal_with_case_hypotheses(task.task_id, body.get("proposal"))
        if task.analysis_mode == "connected" and "flow_plan" in body:
            raise WorkbenchApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "browser-authored flow_plan is no longer accepted; the backend planner owns connected runs",
            )
        flow_plan = self._backend_connected_flow_plan(task, data_path, document_paths) if task.analysis_mode == "connected" else None
        first_event = threading.Event()
        cancel = threading.Event()
        state: dict[str, str] = {}

        def observe(event: RunEvent) -> None:
            if first_event.is_set():
                return
            state["run_id"] = event.run_id
            with self._run_lock:
                self._run_controls[event.run_id] = cancel
                self._run_threads[event.run_id] = threading.current_thread()
            first_event.set()

        def execute() -> None:
            try:
                if flow_plan is None:
                    DemoFlowRunner(self.store).run(
                        task,
                        data_path,
                        document_paths,
                        proposal,
                        on_event=observe,
                        cancelled=cancel.is_set,
                    )
                else:
                    ConnectedFlowRunner(self.store).run(
                        task,
                        data_path,
                        document_paths,
                        flow_plan,
                        proposal,
                        on_event=observe,
                        cancelled=cancel.is_set,
                    )
            except FlowCancelled:
                pass
            except Exception:
                # The runner persists a bounded terminal failure event for clients.
                pass
            finally:
                run_id = state.get("run_id")
                if run_id is not None:
                    with self._run_lock:
                        self._run_controls.pop(run_id, None)
                        self._run_threads.pop(run_id, None)

        thread = threading.Thread(
            target=execute,
            name=f"analysis-{task.task_id}",
            daemon=True,
        )
        thread.start()
        if not first_event.wait(timeout=2.0):
            raise WorkbenchApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "analysis run did not start")
        run_id = state["run_id"]
        run = self.store.get_run(run_id)
        if run is None:
            raise WorkbenchApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "analysis run is unavailable")
        return {
            "accepted": True,
            "run": run.to_dict(),
            "stream_url": f"/api/workbench/runs/{run_id}/stream",
        }

    def _execution_inputs(self, task: AnalysisTask) -> tuple[Path, tuple[Path, ...]]:
        dataset = next((ref for ref in reversed(task.snapshot_refs) if ref.kind == "dataset"), None)
        if dataset is None:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "analysis run requires a dataset snapshot")
        data_path = self.store.snapshot_path(dataset)
        if data_path is None or _file_digest(data_path) != dataset.sha256:
            raise WorkbenchApiError(HTTPStatus.CONFLICT, "dataset snapshot is unavailable or changed")
        document_paths: list[Path] = []
        for ref in task.snapshot_refs:
            if ref.kind != "document":
                continue
            path = self.store.snapshot_path(ref)
            if path is None or _file_digest(path) != ref.sha256:
                raise WorkbenchApiError(HTTPStatus.CONFLICT, "document snapshot is unavailable or changed")
            document_paths.append(path)
        return data_path, tuple(document_paths)

    def _owned_task(self, owner_id: str, task_id: str) -> AnalysisTask:
        task = self.store.get_task_for_owner(task_id, owner_id)
        if task is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "task not found")
        return task

    def _proposal_with_case_hypotheses(self, task_id: str, proposal: object) -> object:
        if proposal is not None and not isinstance(proposal, Mapping):
            return proposal
        if isinstance(proposal, Mapping) and proposal.get("hypotheses") not in (None, []):
            return proposal
        artifact = self.store.get_task_artifact(task_id, "flagship_case")
        if not isinstance(artifact, Mapping) or artifact.get("journey") != "demo":
            return proposal
        manifest = artifact.get("demo_flow")
        if not isinstance(manifest, Mapping) or manifest.get("use_bundled_hypotheses") is not True:
            return proposal
        hypotheses = artifact.get("hypotheses") if isinstance(artifact, Mapping) else None
        raw_items = hypotheses.get("hypotheses") if isinstance(hypotheses, Mapping) else None
        if not isinstance(raw_items, list):
            return proposal
        seeded = []
        for item in raw_items[:20]:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str) or not isinstance(item.get("text"), str):
                continue
            hypothesis = {"hypothesis_id": item.get("id"), "text": item.get("text")}
            if isinstance(item.get("clauses"), list):
                hypothesis["clauses"] = item.get("clauses")
            seeded.append(hypothesis)
        return {"hypotheses": seeded}


def _body(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "request must be an object")
    return payload


def _analysis_journey(analysis_mode: object, agent_provider: object) -> None:
    if analysis_mode not in {"demo", "connected"}:
        raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "analysis_mode must be demo or connected")
    if analysis_mode == "connected" and (not isinstance(agent_provider, str) or not agent_provider.strip()):
        raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "connected analysis requires an agent_provider")
    if analysis_mode == "demo" and agent_provider is not None:
        raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "demo analysis cannot set an agent_provider")


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
