from pathlib import Path
import hashlib
import tempfile
import unittest

from data2doc2data.flow_engine import (
    ConnectedFlowRunner,
    DemoFlowRunner,
    FlowCancelled,
    FlowPlanError,
    validate_flow_plan,
)
from data2doc2data.knowledge import KnowledgeLedger
from data2doc2data.workspace import AnalysisTask, SnapshotRef
from data2doc2data.workspace_store import WorkspaceStore


class FlowEngineTests(unittest.TestCase):
    def test_demo_runner_emits_and_persists_a_live_cross_reasoning_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "strategy.md"
            data.write_text(
                "date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,8\n",
                encoding="utf-8",
            )
            document.write_text(
                "# 策略\n\n主张：revenue 目标为 120 万元。\n\n主张：revenue 目标为 100 万元。\n",
                encoding="utf-8",
            )
            task = _task(data, document)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            observed = []
            graph_sizes = []

            def observe(event):
                observed.append(event)
                if event.kind in {"node.added", "edge.added"}:
                    graph = store.get_run_artifact(event.run_id, "evidence_graph")
                    graph_sizes.append((len(graph["nodes"]), len(graph["edges"])))

            result = DemoFlowRunner(store).run(task, data, (document,), on_event=observe)

            kinds = [event.kind for event in observed]
            self.assertEqual(kinds[0], "run.started")
            self.assertIn("plan.created", kinds)
            self.assertIn("step.added", kinds)
            self.assertIn("tool.started", kinds)
            self.assertIn("tool.result", kinds)
            self.assertIn("node.added", kinds)
            self.assertIn("edge.added", kinds)
            self.assertIn("edge.activated", kinds)
            self.assertTrue({"conflict.detected", "plan.revised"} & set(kinds))
            self.assertIn("knowledge.candidate", kinds)
            self.assertLess(kinds.index("report.generated"), kinds.index("run.completed"))
            self.assertEqual(kinds[-1], "run.completed")
            self.assertEqual(observed, list(result.events))
            self.assertEqual(store.events_after(result.run.run_id), result.events)
            self.assertEqual(
                [event.sequence for event in observed],
                list(range(1, len(observed) + 1)),
            )
            self.assertGreater(len(set(graph_sizes)), 1)
            knowledge = KnowledgeLedger(store).latest(task.task_id)
            self.assertEqual(len(knowledge), 1)
            self.assertEqual(knowledge[0].state, "candidate")
            self.assertEqual(KnowledgeLedger(store).verified_facts(task.task_id), ())

    def test_connected_runner_accepts_only_a_bounded_registered_dag(self):
        payload = {
            "plan_id": "connected-plan",
            "steps": [
                {
                    "step_id": "inspect",
                    "tool": "inspect_sources",
                    "purpose": "识别数据与文本",
                    "dependencies": [],
                    "arguments": {"source_role": "all"},
                },
                {
                    "step_id": "profile",
                    "tool": "profile_data",
                    "purpose": "计算数据画像",
                    "dependencies": ["inspect"],
                    "arguments": {"source_role": "dataset"},
                },
            ],
        }

        plan = validate_flow_plan(payload, ConnectedFlowRunner.REGISTERED_TOOLS)

        self.assertEqual(plan.plan_id, "connected-plan")
        self.assertEqual([step.step_id for step in plan.steps], ["inspect", "profile"])

    def test_demo_runner_persists_an_interrupted_terminal_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "notes.md"
            data.write_text(
                "date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,8\n",
                encoding="utf-8",
            )
            document.write_text("# Notes\n", encoding="utf-8")
            task = _task(data, document)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            with self.assertRaises(FlowCancelled):
                DemoFlowRunner(store).run(task, data, (document,), cancelled=lambda: True)

            run = store.list_runs(task.task_id)[0]
            self.assertEqual(run.status.value, "interrupted")
            self.assertEqual(store.events_after(run.run_id)[-1].kind, "run.interrupted")

    def test_connected_runner_rejects_unknown_tools_cycles_and_oversized_plans(self):
        base = {
            "plan_id": "bad-plan",
            "steps": [
                {
                    "step_id": "unsafe",
                    "tool": "shell",
                    "purpose": "run arbitrary code",
                    "dependencies": [],
                    "arguments": {},
                }
            ],
        }
        with self.assertRaisesRegex(FlowPlanError, "registered tool"):
            validate_flow_plan(base, ConnectedFlowRunner.REGISTERED_TOOLS)

        cycle = {
            "plan_id": "cycle-plan",
            "steps": [
                {"step_id": "a", "tool": "inspect_sources", "purpose": "a", "dependencies": ["b"], "arguments": {}},
                {"step_id": "b", "tool": "profile_data", "purpose": "b", "dependencies": ["a"], "arguments": {}},
            ],
        }
        with self.assertRaisesRegex(FlowPlanError, "acyclic"):
            validate_flow_plan(cycle, ConnectedFlowRunner.REGISTERED_TOOLS)

        oversized = {
            "plan_id": "large-plan",
            "steps": [
                {
                    "step_id": f"step-{index}",
                    "tool": "inspect_sources",
                    "purpose": "inspect",
                    "dependencies": [],
                    "arguments": {},
                }
                for index in range(33)
            ],
        }
        with self.assertRaisesRegex(FlowPlanError, "32"):
            validate_flow_plan(oversized, ConnectedFlowRunner.REGISTERED_TOOLS)

    def test_connected_runner_executes_each_approved_plan_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "notes.md"
            data.write_text(
                "date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,8\n",
                encoding="utf-8",
            )
            document.write_text("# Notes\n", encoding="utf-8")
            task = _task(data, document)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            plan = {
                "plan_id": "agent-plan",
                "steps": [
                    {
                        "step_id": "inspect",
                        "tool": "inspect_sources",
                        "purpose": "inspect",
                        "dependencies": [],
                        "arguments": {},
                    },
                    {
                        "step_id": "profile",
                        "tool": "profile_data",
                        "purpose": "profile",
                        "dependencies": ["inspect"],
                        "arguments": {},
                    },
                    {
                        "step_id": "query",
                        "tool": "query_data",
                        "purpose": "query revenue",
                        "dependencies": ["profile"],
                        "arguments": {"metric": "revenue"},
                    },
                    {
                        "step_id": "extract",
                        "tool": "extract_claims",
                        "purpose": "extract",
                        "dependencies": ["inspect"],
                        "arguments": {},
                    },
                    {
                        "step_id": "align",
                        "tool": "align_evidence",
                        "purpose": "align",
                        "dependencies": ["profile", "extract"],
                        "arguments": {},
                    },
                ],
            }

            result = ConnectedFlowRunner(store).run(task, data, (document,), plan)

        completed_tools = [event.summary["tool"] for event in result.events if event.kind == "tool.result"]
        self.assertEqual(
            completed_tools,
            ["inspect_sources", "profile_data", "query_data", "extract_claims", "align_evidence"],
        )


def _task(data: Path, document: Path) -> AnalysisTask:
    dataset = SnapshotRef("dataset", "dataset-1", hashlib.sha256(data.read_bytes()).hexdigest())
    text = SnapshotRef("document", "document-1", hashlib.sha256(document.read_bytes()).hexdigest())
    return AnalysisTask.create("task-1", "收入调查", "解释收入下降", (dataset, text))


if __name__ == "__main__":
    unittest.main()
