"""Application service for authenticated workbench task APIs."""

from __future__ import annotations

from http import HTTPStatus
import hashlib
from pathlib import Path
import secrets
import re
import threading
from typing import Any, Mapping

from .run_events import RunEvent, RunEventError
from .data_profile import DataProfileError, build_default_dashboard, profile_standard_csv
from .documents import build_document_corpus
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
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store
        self._retry_lock = threading.Lock()

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
            task = AnalysisTask.create(
                task_id=f"task-{secrets.token_hex(12)}",
                title=body.get("title", ""),
                goal=body.get("goal", ""),
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
            refs = { (ref.kind, ref.snapshot_id): ref for ref in current.snapshot_refs }
            refs.update({(ref.kind, ref.snapshot_id): ref for ref in supplied})
            updated = AnalysisTask(
                task_id=current.task_id,
                title=current.title,
                goal=current.goal,
                status=current.status,
                snapshot_refs=tuple(refs.values()),
                created_at=current.created_at,
                updated_at=_utc_now(),
            )
            self.store.save_task(updated)
        except (WorkspaceContractError, WorkspaceStoreError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"task": updated.to_dict()}

    def start_run(self, owner_id: str, task_id: str, payload: object) -> dict[str, object]:
        body = _body(payload)
        task = self._owned_task(owner_id, task_id)
        if body.get("execute") is True:
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
            try:
                result = AnalysisOrchestrator(self.store).run(
                    task, data_path, tuple(document_paths), body.get("proposal")
                )
                graph = result.evidence_graph.to_dict()
                self.store.save_run_artifact(result.run.run_id, "evidence_graph", graph)
            except (ValueError, WorkspaceStoreError) as exc:
                raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
            return {
                "run": result.run.to_dict(),
                "events": [event.to_dict() for event in result.events],
                "evidence_graph": graph,
            }
        try:
            run = AnalysisRun.create(
                run_id=f"run-{secrets.token_hex(12)}",
                task_id=task.task_id,
                snapshot_refs=task.snapshot_refs,
            ).transition(RunStatus.RUNNING)
            event = RunEvent.create(
                run.run_id, 1, "run.started", "setup", {"snapshot_count": len(run.snapshot_refs)}
            )
            self.store.create_run(run, event)
        except (WorkspaceContractError, WorkspaceStoreError, RunEventError) as exc:
            raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
        return {"run": run.to_dict()}

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
        return {
            "run": run.to_dict(),
            "events": [event.to_dict() for event in self.store.events_after(run_id)],
            "evidence_graph": graph,
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
        text_dashboard = build_text_dashboard(
            build_document_corpus(combined_paths, f"corpus-{task_id}")
        ).to_dict()
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
        combined = self.task_dashboard(owner_id, task_id)
        runs = self.store.list_runs(task_id)
        graph = None
        for run in runs:
            candidate = self.store.get_run_artifact(run.run_id, "evidence_graph")
            if isinstance(candidate, Mapping):
                graph = candidate
                break
        return build_html_report(
            task,
            combined.get("dashboard") if isinstance(combined.get("dashboard"), Mapping) else None,
            combined.get("text_dashboard") if isinstance(combined.get("text_dashboard"), Mapping) else None,
            graph if isinstance(graph, Mapping) else None,
            run_count=len(runs),
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

    def _owned_task(self, owner_id: str, task_id: str) -> AnalysisTask:
        task = self.store.get_task_for_owner(task_id, owner_id)
        if task is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "task not found")
        return task


def _body(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WorkbenchApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "request must be an object")
    return payload


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
