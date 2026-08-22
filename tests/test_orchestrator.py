from pathlib import Path
import tempfile
import unittest

from data2doc2data.orchestrator import AnalysisOrchestrator
from data2doc2data.workspace import AnalysisTask, SnapshotRef
from data2doc2data.workspace_store import WorkspaceStore


class OrchestratorTests(unittest.TestCase):
    def test_model_free_run_emits_ordered_events_and_pins_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "strategy.md"
            data.write_text("date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,8\n", encoding="utf-8")
            document.write_text("# 策略\n\n主张：收入目标为 120 万元。\n\n主张：收入目标为 100 万元。\n", encoding="utf-8")
            digest = __import__("hashlib").sha256
            snapshot = SnapshotRef("dataset", "dataset-1", digest(data.read_bytes()).hexdigest())
            document_snapshot = SnapshotRef("document", "document-1", digest(document.read_bytes()).hexdigest())
            task = AnalysisTask.create("task-1", "收入调查", "解释收入下降", (snapshot, document_snapshot))
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            result = AnalysisOrchestrator(store).run(task, data, (document,))

        self.assertEqual(result.run.status.value, "completed")
        self.assertEqual(result.run.snapshot_refs, (snapshot, document_snapshot))
        kinds = [event.kind for event in result.events]
        self.assertEqual(kinds[0], "run.started")
        self.assertIn("data.profiled", kinds)
        self.assertIn("chart.spec.created", kinds)
        self.assertIn("document.indexed", kinds)
        self.assertIn("claim.extracted", kinds)
        self.assertIn("evidence.linked", kinds)
        self.assertIn("contradicts", [edge.relationship for edge in result.evidence_graph.edges])
        self.assertEqual(kinds[-1], "run.completed")
        self.assertEqual([event.sequence for event in result.events], list(range(1, len(result.events) + 1)))
        self.assertNotIn("chain_of_thought", str([event.to_dict() for event in result.events]))

    def test_failed_run_is_persisted_with_a_terminal_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "bad.csv"
            data.write_text("wrong,columns\n1,2\n", encoding="utf-8")
            digest = __import__("hashlib").sha256(data.read_bytes()).hexdigest()
            task = AnalysisTask.create("task-1", "调查", "解释变化", (SnapshotRef("dataset", "dataset-1", digest),))
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            with self.assertRaises(Exception):
                AnalysisOrchestrator(store).run(task, data, ())

            run = store.list_runs("task-1")[0]
            events = store.events_after(run.run_id)
        self.assertEqual(run.status.value, "failed")
        self.assertEqual(events[-1].kind, "run.failed")

    def test_structured_hypotheses_are_visible_without_private_reasoning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            data.write_text("date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,8\n", encoding="utf-8")
            digest = __import__("hashlib").sha256(data.read_bytes()).hexdigest()
            task = AnalysisTask.create("task-1", "调查", "解释变化", (SnapshotRef("dataset", "dataset-1", digest),))
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            result = AnalysisOrchestrator(store).run(
                task,
                data,
                (),
                proposal={"hypotheses": [{"hypothesis_id": "hypothesis-price", "text": "价格调整影响收入"}]},
            )

        node = next(node for node in result.evidence_graph.nodes if node.node_id == "hypothesis-price")
        self.assertEqual(node.kind, "hypothesis")
        self.assertEqual(node.status, "pending")
        self.assertIn("hypothesis.created", [event.kind for event in result.events])
        self.assertIn("validation.completed", [event.kind for event in result.events])


if __name__ == "__main__":
    unittest.main()
