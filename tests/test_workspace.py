import unittest
from dataclasses import FrozenInstanceError

from data2doc2data.workspace import (
    AnalysisRun,
    AnalysisTask,
    RunStatus,
    SnapshotRef,
    TaskStatus,
    WorkspaceContractError,
)


class WorkspaceContractTests(unittest.TestCase):
    def test_task_round_trip_keeps_versioned_immutable_snapshot_refs(self):
        snapshot = SnapshotRef(
            kind="dataset",
            snapshot_id="dataset-20260823",
            sha256="a" * 64,
        )
        task = AnalysisTask.create(
            task_id="task-1",
            title="区域增长复盘",
            goal="找出收入下降的主要原因",
            snapshot_refs=(snapshot,),
            now="2026-08-23T08:00:00Z",
        )

        restored = AnalysisTask.from_dict(task.to_dict())

        self.assertEqual(restored, task)
        self.assertEqual(restored.contract_version, 1)
        self.assertEqual(restored.status, TaskStatus.ACTIVE)
        with self.assertRaises(FrozenInstanceError):
            snapshot.snapshot_id = "changed"

    def test_task_requires_stable_identifiers_and_nonempty_goal(self):
        with self.assertRaisesRegex(WorkspaceContractError, "task_id"):
            AnalysisTask.create(task_id="bad/id", title="Title", goal="Goal")
        with self.assertRaisesRegex(WorkspaceContractError, "goal"):
            AnalysisTask.create(task_id="task-1", title="Title", goal="  ")

    def test_task_status_transition_is_explicit_and_timestamped(self):
        task = AnalysisTask.create(
            task_id="task-1",
            title="复盘",
            goal="解释变化",
            now="2026-08-23T08:00:00Z",
        )

        archived = task.transition(TaskStatus.ARCHIVED, now="2026-08-23T09:00:00Z")

        self.assertEqual(archived.status, TaskStatus.ARCHIVED)
        self.assertEqual(archived.updated_at, "2026-08-23T09:00:00Z")
        with self.assertRaisesRegex(WorkspaceContractError, "transition"):
            archived.transition(TaskStatus.ACTIVE, now="2026-08-23T10:00:00Z")

    def test_run_pins_snapshots_and_allows_only_valid_transitions(self):
        snapshot = SnapshotRef("document", "doc-1", "b" * 64)
        run = AnalysisRun.create(
            run_id="run-1",
            task_id="task-1",
            snapshot_refs=(snapshot,),
            now="2026-08-23T08:00:00Z",
        )

        running = run.transition(RunStatus.RUNNING, now="2026-08-23T08:01:00Z")
        completed = running.transition(RunStatus.COMPLETED, now="2026-08-23T08:02:00Z")

        self.assertEqual(completed.snapshot_refs, (snapshot,))
        self.assertEqual(AnalysisRun.from_dict(completed.to_dict()), completed)
        self.assertEqual(completed.completed_at, "2026-08-23T08:02:00Z")
        with self.assertRaisesRegex(WorkspaceContractError, "transition"):
            completed.transition(RunStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
