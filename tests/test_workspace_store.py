from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from data2doc2data.config import ProfileStore
from data2doc2data.run_events import RunEvent, RunEventError
from data2doc2data.workspace import AnalysisRun, AnalysisTask, RunStatus, SnapshotRef, TaskStatus
from data2doc2data.workspace_store import WorkspaceStore, WorkspaceStoreError


class WorkspaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "state" / "workbench.sqlite3"
        self.store = WorkspaceStore(self.path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_initialization_creates_private_versioned_database(self):
        self.store.initialize()

        with closing(sqlite3.connect(self.path)) as connection:
            version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0]

        self.assertEqual(version, "1")
        self.assertTrue(self.store.foreign_keys_enabled())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_task_crud_keeps_versioned_contracts(self):
        task = AnalysisTask.create("task-1", "收入复盘", "解释收入下降", now="2026-08-23T08:00:00Z")

        self.store.save_task(task)
        archived = task.transition(TaskStatus.ARCHIVED, now="2026-08-23T09:00:00Z")
        self.store.save_task(archived)

        self.assertEqual(self.store.get_task("task-1"), archived)
        self.assertEqual(self.store.list_tasks(), (archived,))
        self.assertTrue(self.store.delete_task("task-1"))
        self.assertIsNone(self.store.get_task("task-1"))
        self.assertFalse(self.store.delete_task("task-1"))

    def test_runs_pin_snapshot_references_and_cascade_events(self):
        snapshot = SnapshotRef("dataset", "dataset-1", "a" * 64)
        task = AnalysisTask.create(
            "task-1", "收入复盘", "解释收入下降", (snapshot,), now="2026-08-23T08:00:00Z"
        )
        run = AnalysisRun.create("run-1", task.task_id, (snapshot,), now="2026-08-23T08:01:00Z")
        self.store.save_task(task)
        self.store.save_run(run)

        running = run.transition(RunStatus.RUNNING, now="2026-08-23T08:02:00Z")
        self.store.save_run(running)

        self.assertEqual(self.store.get_run("run-1"), running)
        self.assertEqual(self.store.list_runs("task-1"), (running,))
        with self.assertRaisesRegex(WorkspaceStoreError, "status transition"):
            self.store.save_run(run)
        changed = AnalysisRun.create(
            "run-1",
            task.task_id,
            (SnapshotRef("dataset", "dataset-2", "b" * 64),),
            now="2026-08-23T08:01:00Z",
        )
        with self.assertRaisesRegex(WorkspaceStoreError, "snapshot"):
            self.store.save_run(changed)

    def test_events_are_appended_transactionally_and_replayed_in_order(self):
        task = AnalysisTask.create("task-1", "复盘", "解释变化", now="2026-08-23T08:00:00Z")
        run = AnalysisRun.create("run-1", "task-1", now="2026-08-23T08:01:00Z")
        first = RunEvent.create("run-1", 1, "run.started", "setup", {})
        second = RunEvent.create("run-1", 2, "data.profiled", "profile", {"row_count": 12})
        self.store.save_task(task)
        self.store.save_run(run)

        self.store.append_event(first)
        self.store.append_event(second)

        self.assertEqual(self.store.events_after("run-1", 0), (first, second))
        self.assertEqual(self.store.events_after("run-1", 1), (second,))
        with self.assertRaisesRegex((RunEventError, WorkspaceStoreError), "sequence|contiguous"):
            self.store.append_event(RunEvent.create("run-1", 4, "run.completed", "finish", {}))
        self.assertEqual(self.store.events_after("run-1", 0), (first, second))

    def test_run_and_initial_event_are_created_atomically(self):
        task = AnalysisTask.create("task-1", "复盘", "解释变化", now="2026-08-23T08:00:00Z")
        run = AnalysisRun.create("run-1", "task-1", now="2026-08-23T08:01:00Z")
        self.store.save_task(task)

        with self.assertRaisesRegex(RunEventError, "sequence"):
            self.store.create_run(run, RunEvent.create("run-1", 2, "run.started", "setup", {}))
        self.assertIsNone(self.store.get_run("run-1"))

        event = RunEvent.create("run-1", 1, "run.started", "setup", {})
        self.store.create_run(run, event)

        self.assertEqual(self.store.get_run("run-1"), run)
        self.assertEqual(self.store.events_after("run-1"), (event,))

    def test_missing_parent_and_corrupt_database_errors_are_clear(self):
        missing_run = AnalysisRun.create("run-1", "missing-task", now="2026-08-23T08:00:00Z")
        with self.assertRaisesRegex(WorkspaceStoreError, "task"):
            self.store.save_run(missing_run)

        corrupt_path = Path(self.temporary_directory.name) / "corrupt.sqlite3"
        corrupt_path.write_text("not a database", encoding="utf-8")
        with self.assertRaisesRegex(WorkspaceStoreError, "database"):
            WorkspaceStore(corrupt_path).list_tasks()

    def test_profile_json_and_workspace_database_can_coexist(self):
        profile_store = ProfileStore(Path(self.temporary_directory.name) / "config" / "config.json")

        self.assertEqual(profile_store.workspace_database_path.name, "workbench.sqlite3")
        self.assertEqual(profile_store.workspace_database_path.parent, profile_store.path.parent)
        self.assertFalse(profile_store.workspace_database_path.exists())


if __name__ == "__main__":
    unittest.main()
