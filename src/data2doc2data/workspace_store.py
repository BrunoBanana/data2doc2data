"""SQLite persistence for local workbench tasks, runs, and observable events."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Iterator

from .run_events import RunEvent, RunEventError
from .workspace import AnalysisRun, AnalysisTask, SnapshotRef, WorkspaceContractError


SCHEMA_VERSION = 1


class WorkspaceStoreError(ValueError):
    """Raised when the local workbench metadata database cannot be used safely."""


class WorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._lock = threading.RLock()

    def initialize(self) -> None:
        with self._connection():
            pass

    def foreign_keys_enabled(self) -> bool:
        with self._connection() as connection:
            return connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def save_task(self, task: AnalysisTask) -> AnalysisTask:
        payload = _json(task.to_dict())
        with self._lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tasks (task_id, status, updated_at, payload)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload = excluded.payload
                """,
                (task.task_id, task.status.value, task.updated_at, payload),
            )
        return task

    def assign_task_owner(self, task_id: str, owner_id: str) -> None:
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO task_owners (task_id, owner_id) VALUES (?, ?)", (task_id, owner_id)
                )
            except sqlite3.IntegrityError as exc:
                existing = connection.execute(
                    "SELECT owner_id FROM task_owners WHERE task_id = ?", (task_id,)
                ).fetchone()
                if existing is not None and existing[0] == owner_id:
                    return
                raise WorkspaceStoreError("task owner cannot be changed") from exc

    def get_task_for_owner(self, task_id: str, owner_id: str) -> AnalysisTask | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT tasks.payload FROM tasks
                JOIN task_owners USING(task_id)
                WHERE tasks.task_id = ? AND task_owners.owner_id = ?
                """,
                (task_id, owner_id),
            ).fetchone()
        return None if row is None else AnalysisTask.from_dict(json.loads(row[0]))

    def list_tasks_for_owner(self, owner_id: str) -> tuple[AnalysisTask, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT tasks.payload FROM tasks
                JOIN task_owners USING(task_id)
                WHERE task_owners.owner_id = ?
                ORDER BY tasks.updated_at DESC, tasks.task_id
                """,
                (owner_id,),
            ).fetchall()
        return tuple(AnalysisTask.from_dict(json.loads(row[0])) for row in rows)

    def get_task(self, task_id: str) -> AnalysisTask | None:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return None if row is None else AnalysisTask.from_dict(json.loads(row[0]))

    def list_tasks(self) -> tuple[AnalysisTask, ...]:
        with self._connection() as connection:
            rows = connection.execute("SELECT payload FROM tasks ORDER BY updated_at DESC, task_id").fetchall()
        return tuple(AnalysisTask.from_dict(json.loads(row[0])) for row in rows)

    def delete_task(self, task_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        return cursor.rowcount > 0

    def register_snapshot(self, snapshot: SnapshotRef, path: Path) -> None:
        resolved = path.expanduser().resolve()
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT kind, sha256, path FROM snapshot_assets WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            expected = (snapshot.kind, snapshot.sha256, str(resolved))
            if existing is not None:
                if tuple(existing) != expected:
                    raise WorkspaceStoreError("snapshot registration cannot be changed")
                return
            if not resolved.is_file():
                raise WorkspaceStoreError("snapshot path must be an existing file")
            connection.execute(
                "INSERT INTO snapshot_assets (snapshot_id, kind, sha256, path) VALUES (?, ?, ?, ?)",
                (snapshot.snapshot_id, snapshot.kind, snapshot.sha256, str(resolved)),
            )

    def snapshot_path(self, snapshot: SnapshotRef) -> Path | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT path FROM snapshot_assets WHERE snapshot_id = ? AND kind = ? AND sha256 = ?",
                (snapshot.snapshot_id, snapshot.kind, snapshot.sha256),
            ).fetchone()
        return None if row is None else Path(row[0])

    def save_run(self, run: AnalysisRun) -> AnalysisRun:
        payload = _json(run.to_dict())
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                "SELECT task_id, snapshot_refs, payload FROM runs WHERE run_id = ?", (run.run_id,)
            ).fetchone()
            snapshot_refs = _json([ref.to_dict() for ref in run.snapshot_refs])
            if existing is not None and (existing[0] != run.task_id or existing[1] != snapshot_refs):
                raise WorkspaceStoreError("run task and snapshot references are immutable")
            if existing is not None:
                saved_run = AnalysisRun.from_dict(json.loads(existing[2]))
                if saved_run.status != run.status:
                    try:
                        saved_run.transition(run.status)
                    except WorkspaceContractError as exc:
                        raise WorkspaceStoreError(f"invalid persisted status transition: {exc}") from exc
            try:
                connection.execute(
                    """
                    INSERT INTO runs (run_id, task_id, status, created_at, snapshot_refs, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        status = excluded.status,
                        payload = excluded.payload
                    """,
                    (run.run_id, run.task_id, run.status.value, run.created_at, snapshot_refs, payload),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkspaceStoreError(f"cannot save run because its task does not exist: {run.task_id}") from exc
        return run

    def create_run(self, run: AnalysisRun, initial_event: RunEvent) -> AnalysisRun:
        if initial_event.run_id != run.run_id or initial_event.sequence != 1:
            raise RunEventError("initial event sequence must be 1 for the same run")
        if initial_event.kind != "run.started":
            raise RunEventError("initial event kind must be run.started")
        snapshot_refs = _json([ref.to_dict() for ref in run.snapshot_refs])
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO runs (run_id, task_id, status, created_at, snapshot_refs, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.run_id,
                        run.task_id,
                        run.status.value,
                        run.created_at,
                        snapshot_refs,
                        _json(run.to_dict()),
                    ),
                )
                connection.execute(
                    "INSERT INTO run_events (run_id, sequence, created_at, payload) VALUES (?, ?, ?, ?)",
                    (initial_event.run_id, initial_event.sequence, initial_event.created_at, _json(initial_event.to_dict())),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise WorkspaceStoreError(f"cannot create run for task: {run.task_id}") from exc
            except Exception:
                connection.rollback()
                raise
        return run

    def get_run(self, run_id: str) -> AnalysisRun | None:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return None if row is None else AnalysisRun.from_dict(json.loads(row[0]))

    def save_run_artifact(self, run_id: str, kind: str, payload: object) -> None:
        if kind not in {"evidence_graph"}:
            raise WorkspaceStoreError("unsupported run artifact kind")
        encoded = _json(payload)
        if len(encoded.encode("utf-8")) > 2_000_000:
            raise WorkspaceStoreError("run artifact is too large")
        with self._lock, self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO run_artifacts (run_id, kind, payload) VALUES (?, ?, ?) ON CONFLICT(run_id, kind) DO UPDATE SET payload = excluded.payload",
                    (run_id, kind, encoded),
                )
            except sqlite3.IntegrityError as exc:
                raise WorkspaceStoreError("cannot save artifact for unknown run") from exc

    def get_run_artifact(self, run_id: str, kind: str) -> object | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM run_artifacts WHERE run_id = ? AND kind = ?", (run_id, kind)
            ).fetchone()
        return None if row is None else json.loads(row[0])

    def list_runs(self, task_id: str) -> tuple[AnalysisRun, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM runs WHERE task_id = ? ORDER BY created_at DESC, run_id", (task_id,)
            ).fetchall()
        return tuple(AnalysisRun.from_dict(json.loads(row[0])) for row in rows)

    def owner_can_access_run(self, run_id: str, owner_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM runs
                JOIN task_owners USING(task_id)
                WHERE runs.run_id = ? AND task_owners.owner_id = ?
                """,
                (run_id, owner_id),
            ).fetchone()
        return row is not None

    def append_event(self, event: RunEvent) -> RunEvent:
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                latest = connection.execute(
                    "SELECT MAX(sequence) FROM run_events WHERE run_id = ?", (event.run_id,)
                ).fetchone()[0]
                expected = 1 if latest is None else latest + 1
                if event.sequence != expected:
                    raise RunEventError(f"event sequence must be contiguous; expected {expected}")
                connection.execute(
                    "INSERT INTO run_events (run_id, sequence, created_at, payload) VALUES (?, ?, ?, ?)",
                    (event.run_id, event.sequence, event.created_at, _json(event.to_dict())),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise WorkspaceStoreError(f"cannot append event for unknown run: {event.run_id}") from exc
            except Exception:
                connection.rollback()
                raise
        return event

    def events_after(self, run_id: str, sequence: int = 0, limit: int = 1000) -> tuple[RunEvent, ...]:
        if not isinstance(sequence, int) or sequence < 0:
            raise WorkspaceStoreError("sequence must be a non-negative integer")
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise WorkspaceStoreError("limit must be between 1 and 1000")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM run_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence ASC LIMIT ?
                """,
                (run_id, sequence, limit),
            ).fetchall()
        return tuple(RunEvent.from_dict(json.loads(row[0])) for row in rows)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 5000")
            self._ensure_schema(connection)
            os.chmod(self.path, 0o600)
            yield connection
        except (OSError, sqlite3.DatabaseError, json.JSONDecodeError, TypeError, ValueError) as exc:
            if isinstance(exc, (WorkspaceStoreError, RunEventError)):
                raise
            raise WorkspaceStoreError(f"cannot use workspace database: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS task_owners (
                task_id TEXT PRIMARY KEY REFERENCES tasks(task_id) ON DELETE CASCADE,
                owner_id TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS task_owners_owner ON task_owners(owner_id, task_id);
            CREATE TABLE IF NOT EXISTS snapshot_assets (
                snapshot_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                snapshot_refs TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS runs_task_created ON runs(task_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                sequence INTEGER NOT NULL CHECK(sequence > 0),
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(run_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS run_artifacts (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(run_id, kind)
            );
            """
        )
        row = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO metadata (key, value) VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
            )
        elif row[0] != str(SCHEMA_VERSION):
            raise WorkspaceStoreError(f"unsupported workspace schema version: {row[0]}")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
