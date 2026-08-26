from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from data2doc2data.flow_engine import (
    ConnectedFlowRunner,
    DemoFlowRunner,
    FlowCancelled,
    FlowPlanError,
    validate_flow_plan,
)
from data2doc2data.knowledge import KnowledgeLedger
from data2doc2data.flow_tools import LocalAnalysisTools
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
            self.assertIn("step.started", kinds)
            self.assertIn("step.completed", kinds)
            self.assertIn("tool.started", kinds)
            self.assertIn("tool.result", kinds)
            self.assertIn("node.added", kinds)
            self.assertIn("edge.added", kinds)
            self.assertIn("edge.activated", kinds)
            self.assertTrue({"conflict.detected", "plan.revised"} & set(kinds))
            self.assertIn("knowledge.candidate", kinds)
            self.assertIn("conclusion.created", kinds)
            self.assertIn("cycle.started", kinds)
            self.assertIn("round.planned", kinds)
            self.assertIn("artifact.created", kinds)
            self.assertIn("cycle.completed", kinds)
            self.assertLess(kinds.index("report.generated"), kinds.index("run.completed"))
            self.assertEqual(kinds[-1], "run.completed")
            self.assertEqual(observed, list(result.events))
            self.assertEqual(store.events_after(result.run.run_id), result.events)
            self.assertEqual(
                [event.sequence for event in observed],
                list(range(1, len(observed) + 1)),
            )
            self.assertGreater(len(set(graph_sizes)), 1)
            node_kinds = {node.kind for node in result.evidence_graph.nodes}
            self.assertTrue({"analytical_artifact", "conclusion", "action", "report"} <= node_kinds)
            artifact_dashboard = store.get_run_artifact(result.run.run_id, "artifact_dashboard")
            self.assertTrue(artifact_dashboard["blocks"])
            versioned_graph = store.get_run_artifact_version(result.run.run_id, "evidence_graph")
            self.assertGreater(versioned_graph["revision"], 1)
            self.assertEqual(versioned_graph["payload"], result.evidence_graph.to_dict())
            knowledge = KnowledgeLedger(store).latest(task.task_id)
            self.assertEqual(len(knowledge), 1)
            self.assertEqual(knowledge[0].state, "candidate")
            self.assertEqual(KnowledgeLedger(store).verified_facts(task.task_id), ())
            for event in observed:
                if event.kind in {"step.completed", "tool.result"}:
                    self.assertIsInstance(event.summary.get("duration_ms"), int)
                    self.assertGreaterEqual(event.summary["duration_ms"], 0)

            message_ids = [event.communication.message_id for event in observed]
            self.assertEqual(len(message_ids), len(set(message_ids)))
            self.assertTrue(all(event.communication.trace_id == result.run.run_id for event in observed))
            self.assertEqual(
                (observed[0].communication.sender, observed[0].communication.receiver),
                ("orchestrator", "workbench"),
            )
            seen_messages = {observed[0].communication.message_id}
            for event in observed[1:]:
                self.assertIn(event.communication.causation_id, seen_messages)
                seen_messages.add(event.communication.message_id)

            planned = next(event for event in observed if event.kind == "round.planned")
            self.assertEqual(
                (planned.communication.sender, planned.communication.receiver),
                ("planner.deterministic_demo", "orchestrator"),
            )
            tool_started = next(
                event
                for event in observed
                if event.kind == "tool.started" and event.summary.get("tool") == "inspect_sources"
            )
            tool_result = next(
                event
                for event in observed
                if event.kind == "tool.result" and event.summary.get("tool") == "inspect_sources"
            )
            self.assertEqual(
                (tool_started.communication.sender, tool_started.communication.receiver),
                ("orchestrator", "tool.inspect_sources"),
            )
            self.assertEqual(
                (tool_result.communication.sender, tool_result.communication.receiver),
                ("tool.inspect_sources", "orchestrator"),
            )
            self.assertEqual(tool_result.communication.causation_id, tool_started.communication.message_id)
            node_added = next(event for event in observed if event.kind == "node.added")
            self.assertEqual(node_added.communication.receiver, "evidence_store")
            artifact_created = next(event for event in observed if event.kind == "artifact.created")
            self.assertEqual(
                artifact_created.communication.sender,
                f"tool.{artifact_created.summary['tool']}",
            )
            report_generated = next(event for event in observed if event.kind == "report.generated")
            self.assertEqual(
                (report_generated.communication.sender, report_generated.communication.receiver),
                ("reporter", "workbench"),
            )

    def test_tool_lifecycle_starts_before_the_local_tool_is_invoked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "notes.md"
            data.write_text("date,metric,value\n2026-01-01,revenue,10\n", encoding="utf-8")
            document.write_text("# Notes\n", encoding="utf-8")
            task = _task(data, document)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            observed = []
            lifecycle_at_invocation = []
            original = LocalAnalysisTools.inspect_sources

            def inspected(tools, sources):
                lifecycle_at_invocation.append([event.kind for event in observed])
                return original(tools, sources)

            with patch.object(LocalAnalysisTools, "inspect_sources", inspected):
                DemoFlowRunner(store).run(task, data, (document,), on_event=observed.append)

            self.assertIn("step.started", lifecycle_at_invocation[0])
            self.assertIn("tool.started", lifecycle_at_invocation[0])

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

    def test_connected_registry_accepts_deep_diagnostics_and_rejects_arbitrary_tools(self):
        self.assertIn("detect_anomalies", ConnectedFlowRunner.REGISTERED_TOOLS)
        payload = {
            "plan_id": "unsafe-plan",
            "steps": [
                {
                    "step_id": "python-step",
                    "tool": "python",
                    "purpose": "run arbitrary code",
                    "dependencies": [],
                    "arguments": {},
                }
            ],
        }

        with self.assertRaises(FlowPlanError):
            validate_flow_plan(payload, ConnectedFlowRunner.REGISTERED_TOOLS)

    def test_demo_runner_executes_structured_hypotheses_and_updates_the_graph(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "notes.md"
            data.write_text(
                "date,metric,value\n2026-01-01,revenue,10\n2026-02-01,revenue,12\n",
                encoding="utf-8",
            )
            document.write_text("# Notes\n", encoding="utf-8")
            task = _task(data, document)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            proposal = {
                "hypotheses": [
                    {
                        "hypothesis_id": "hypothesis-revenue",
                        "text": "收入呈上升趋势",
                        "clauses": [{"metric": "revenue", "direction": "up"}],
                    }
                ]
            }

            result = DemoFlowRunner(store).run(task, data, (document,), proposal)

            nodes = {node.node_id: node for node in result.evidence_graph.nodes}
            self.assertEqual(nodes["hypothesis-revenue"].status, "supported")
            self.assertEqual(nodes["validation-1"].status, "supported")
            self.assertTrue(
                any(
                    event.kind == "tool.result" and event.summary.get("tool") == "test_hypothesis"
                    for event in result.events
                )
            )
            self.assertTrue(
                any(
                    event.kind == "node.updated"
                    and event.summary.get("node_id") == "hypothesis-revenue"
                    and event.summary.get("status") == "supported"
                    for event in result.events
                )
            )

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
