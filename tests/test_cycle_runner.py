import hashlib
from pathlib import Path
import tempfile
import unittest

from data2doc2data.cycle_runner import DemoCycleRunner
from data2doc2data.workspace import AnalysisTask, SnapshotRef
from data2doc2data.workspace_store import WorkspaceStore


class DemoCycleRunnerTests(unittest.TestCase):
    def test_demo_cycle_revises_using_a_real_first_round_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, task = _fixture(root)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            result = DemoCycleRunner(store).run(task, data, ())

            self.assertGreaterEqual(len(result.cycle.rounds), 2)
            first, second = result.cycle.rounds[:2]
            self.assertTrue(second.decision.prior_artifact_refs)
            self.assertLessEqual(set(second.decision.prior_artifact_refs), set(first.artifact_refs))
            self.assertEqual(result.cycle.status, "completed")

    def test_resume_uses_checkpoint_without_reexecuting_completed_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, task = _fixture(root)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            runner = DemoCycleRunner(store)

            interrupted = runner.run(task, data, (), interrupt_after_tool_round=1)
            resumed = runner.resume(interrupted.cycle.cycle_id)

            self.assertEqual(interrupted.cycle.status, "interrupted")
            self.assertEqual(store.cycle_execution_count(interrupted.cycle.cycle_id, 1), 1)
            self.assertEqual(resumed.cycle.status, "completed")
            self.assertEqual(store.cycle_execution_count(interrupted.cycle.cycle_id, 1), 1)
            self.assertEqual(resumed.cycle.rounds[0].artifact_refs, interrupted.pending_artifact_refs)


def _fixture(root: Path) -> tuple[Path, AnalysisTask]:
    data = root / "metrics.csv"
    values = [10, 10, 11, 10, 50, 20, 20, 21, 20, 22]
    data.write_text(
        "date,metric,value\n"
        + "".join(f"2026-01-{index:02d},gmv,{value}\n" for index, value in enumerate(values, 1)),
        encoding="utf-8",
    )
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    snapshot = SnapshotRef("dataset", "dataset-cycle", digest)
    task = AnalysisTask.create("task-cycle", "周期诊断", "识别异常与结构变化", (snapshot,))
    return data, task


if __name__ == "__main__":
    unittest.main()
