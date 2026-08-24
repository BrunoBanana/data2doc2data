from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from data2doc2data.config import ProfileStore
from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
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

        self.assertEqual(version, "4")
        self.assertTrue(self.store.foreign_keys_enabled())
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_version_one_database_is_upgraded_in_place(self):
        self.path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")

        self.store.initialize()

        with closing(sqlite3.connect(self.path)) as connection:
            version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0]
            task_artifacts = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'task_artifacts'"
            ).fetchone()
        self.assertEqual(version, "4")
        self.assertEqual(task_artifacts, ("task_artifacts",))

    def test_version_two_database_adds_append_only_knowledge_history(self):
        self.path.parent.mkdir(parents=True)
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata VALUES ('schema_version', '2')")

        self.store.initialize()

        with closing(sqlite3.connect(self.path)) as connection:
            version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0]
            knowledge = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'knowledge_versions'"
            ).fetchone()
        self.assertEqual(version, "4")
        self.assertEqual(knowledge, ("knowledge_versions",))

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
        task = AnalysisTask.create("task-1", "收入复盘", "解释收入下降", (snapshot,), now="2026-08-23T08:00:00Z")
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

    def test_snapshot_paths_are_registered_immutably(self):
        source = Path(self.temporary_directory.name) / "snapshot.csv"
        source.write_text("date,metric,value\n2026-01-01,a,1\n", encoding="utf-8")
        snapshot = SnapshotRef("dataset", "dataset-1", "a" * 64)

        self.store.register_snapshot(snapshot, source)

        self.assertEqual(self.store.snapshot_path(snapshot), source.resolve())
        with self.assertRaisesRegex(WorkspaceStoreError, "cannot be changed"):
            self.store.register_snapshot(snapshot, source.with_name("other.csv"))

    def test_run_artifacts_round_trip_as_bounded_json(self):
        task = AnalysisTask.create("task-1", "复盘", "解释变化")
        run = AnalysisRun.create("run-1", task.task_id)
        self.store.save_task(task)
        self.store.save_run(run)

        self.store.save_run_artifact("run-1", "evidence_graph", {"nodes": [{"id": "n1"}]})

        self.assertEqual(self.store.get_run_artifact("run-1", "evidence_graph"), {"nodes": [{"id": "n1"}]})

    def test_task_artifacts_round_trip_and_follow_task_lifecycle(self):
        task = AnalysisTask.create("task-1", "复盘", "解释变化")
        self.store.save_task(task)

        artifact = {
            "document_snapshot_refs": [],
            "dashboard": {"document_count": 0, "failure_count": 1},
        }
        self.store.save_task_artifact(task.task_id, "text_dashboard", artifact)

        self.assertEqual(self.store.get_task_artifact(task.task_id, "text_dashboard"), artifact)
        self.assertTrue(self.store.delete_task(task.task_id))
        self.assertIsNone(self.store.get_task_artifact(task.task_id, "text_dashboard"))

    def test_profile_json_and_workspace_database_can_coexist(self):
        profile_store = ProfileStore(Path(self.temporary_directory.name) / "config" / "config.json")

        self.assertEqual(profile_store.workspace_database_path.name, "workbench.sqlite3")
        self.assertEqual(profile_store.workspace_database_path.parent, profile_store.path.parent)
        self.assertFalse(profile_store.workspace_database_path.exists())

    def test_analysis_cycle_and_tool_execution_are_persisted_idempotently(self):
        task = AnalysisTask.create("task-cycle-store", "循环", "诊断")
        self.store.save_task(task)
        decision = RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv"}, "检查异常")
        cycle = AnalysisCycle.start("cycle-store").complete_round(
            AnalysisRound.completed(decision, ("artifact-1",))
        )

        self.store.save_analysis_cycle(cycle, task.task_id, {"data_path": "/local/metrics.csv", "document_paths": []})
        first = self.store.save_cycle_execution(
            cycle.cycle_id,
            1,
            "detect_anomalies",
            "execution-key",
            ("artifact-1",),
            {"status": "completed"},
        )
        second = self.store.save_cycle_execution(
            cycle.cycle_id,
            1,
            "detect_anomalies",
            "execution-key",
            ("artifact-1",),
            {"status": "completed"},
        )

        self.assertEqual(self.store.get_analysis_cycle(cycle.cycle_id), cycle)
        self.assertEqual(self.store.get_analysis_cycle_context(cycle.cycle_id)["data_path"], "/local/metrics.csv")
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(self.store.cycle_execution_count(cycle.cycle_id, 1), 1)


if __name__ == "__main__":
    unittest.main()
