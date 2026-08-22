"""Application service for authenticated workbench task APIs."""

from __future__ import annotations

from http import HTTPStatus
import secrets
from typing import Any, Mapping

from .run_events import RunEvent, RunEventError
from .workspace import AnalysisRun, AnalysisTask, RunStatus, SnapshotRef, WorkspaceContractError, _utc_now
from .workspace_store import WorkspaceStore, WorkspaceStoreError


class WorkbenchApiError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class WorkbenchService:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def list_tasks(self, owner_id: str) -> dict[str, object]:
        return {"tasks": [task.to_dict() for task in self.store.list_tasks_for_owner(owner_id)]}

    def get_task(self, owner_id: str, task_id: str) -> dict[str, object]:
        return {"task": self._owned_task(owner_id, task_id).to_dict()}

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
        _body(payload)
        task = self._owned_task(owner_id, task_id)
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
