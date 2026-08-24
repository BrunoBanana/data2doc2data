import hashlib
from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis_cycle import RoundDecision
from data2doc2data.cycle_planner import PlannerResult, PlannerWaiting
from data2doc2data.cycle_runner import ConnectedCycleRunner, DemoCycleRunner
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

    def test_demo_prioritizes_the_strongest_metric_change_and_text_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            document = root / "research.md"
            rows = ["date,metric,value,segment\n"]
            for index in range(1, 11):
                rows.append(f"2026-01-{index:02d},mrr,{100 + index},all\n")
                rows.append(f"2026-01-{index:02d},retention_8w,{0.8 if index < 6 else 0.45},all\n")
            data.write_text("".join(rows), encoding="utf-8")
            document.write_text("# 客户研究\n\n留存下降与首次配置困难同时出现。\n", encoding="utf-8")
            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            task = AnalysisTask.create(
                "task-cross-modal",
                "增长质量诊断",
                "解释留存变化",
                (SnapshotRef("dataset", "dataset-cross-modal", digest),),
            )
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)

            result = DemoCycleRunner(store).run(task, data, (document,))

            self.assertEqual(result.cycle.rounds[0].decision.arguments["metric"], "retention_8w")
            self.assertEqual(result.cycle.rounds[2].decision.tool, "analyze_text")
            text_record = DemoCycleRunner(store).artifacts.load(result.cycle.rounds[2].artifact_refs[0])
            self.assertEqual(text_record["kind"], "text_ml")
            self.assertIn("<svg", text_record["payload"]["word_cloud_svg"])

    def test_connected_cycle_asks_the_agent_after_each_real_artifact(self):
        class Planner:
            def __init__(self):
                self.calls = []

            def decide(self, cycle, artifact_projections, *, provider_resume_id=None):
                self.calls.append((cycle, artifact_projections, provider_resume_id))
                round_number = len(cycle.rounds) + 1
                previous = cycle.rounds[-1].artifact_refs if cycle.rounds else ()
                if round_number == 1:
                    decision = RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv", "window": 5, "threshold": 4}, "先检查异常。")
                elif round_number == 2:
                    decision = RoundDecision(2, "continue", "detect_change_points", {"metric": "gmv", "minimum_window": 3}, "根据异常产物检查结构变化。", previous)
                else:
                    decision = RoundDecision(3, "finish", None, {}, "已有两种独立检验。", previous, stop_reason="evidence_sufficient")
                return PlannerResult(decision, "provider-thread")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, task = _fixture(root)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            planner = Planner()

            result = ConnectedCycleRunner(store, planner).run(task, data, ())

        self.assertEqual(result.cycle.status, "completed")
        self.assertEqual(len(planner.calls), 3)
        self.assertEqual(planner.calls[0][1][0]["tool"], "profile_data")
        self.assertEqual(planner.calls[1][1][-1]["artifact_refs"], list(result.cycle.rounds[0].artifact_refs))
        self.assertEqual(planner.calls[2][2], "provider-thread")

    def test_connected_cycle_reconnects_a_transient_planner_session(self):
        class Planner:
            def __init__(self):
                self.resume_ids = []

            def decide(self, cycle, artifact_projections, *, provider_resume_id=None):
                self.resume_ids.append(provider_resume_id)
                if len(self.resume_ids) == 1:
                    raise PlannerWaiting("temporary disconnect", "recover-thread")
                return PlannerResult(
                    RoundDecision(1, "finish", None, {}, "当前数据无需继续扩展。", stop_reason="evidence_sufficient"),
                    "recover-thread",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, task = _fixture(root)
            store = WorkspaceStore(root / "workbench.sqlite3")
            store.save_task(task)
            events = []
            planner = Planner()

            result = ConnectedCycleRunner(store, planner, on_planner_event=lambda kind, summary: events.append((kind, summary))).run(task, data, ())

        self.assertEqual(result.cycle.status, "completed")
        self.assertEqual(planner.resume_ids, [None, "recover-thread"])
        self.assertEqual([kind for kind, _ in events], ["planner.waiting", "planner.resumed"])


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
