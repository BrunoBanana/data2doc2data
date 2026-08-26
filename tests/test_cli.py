from io import StringIO
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

from data2doc2data.cli import _build_parser, main
from data2doc2data.workspace import AnalysisTask, SnapshotRef
from data2doc2data.workspace_store import WorkspaceStore


class CliTests(unittest.TestCase):
    def test_web_command_defaults_to_the_product_port(self):
        args = _build_parser().parse_args(["web"])

        self.assertEqual(args.command, "web")
        self.assertEqual(args.port, 8781)
        self.assertFalse(args.no_open)

    def test_web_command_accepts_the_product_no_open_flag(self):
        args = _build_parser().parse_args(["web", "--no-open"])

        self.assertTrue(args.no_open)

    def test_legacy_setup_command_keeps_its_port_and_no_browser_alias(self):
        args = _build_parser().parse_args(["setup", "--no-browser"])

        self.assertEqual(args.command, "setup")
        self.assertEqual(args.port, 8765)
        self.assertTrue(args.no_open)

    def test_status_outputs_safe_profile_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(["--config", str(Path(directory) / "config.json"), "status"], stdout=output)

            self.assertEqual(exit_code, 0)
            self.assertIn('"configured": false', output.getvalue())
            self.assertNotIn("data_path", output.getvalue())

    def test_analyze_uses_demo_when_no_profile_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(
                [
                    "--config",
                    str(Path(directory) / "config.json"),
                    "analyze",
                    "--question",
                    "Why did retention fall?",
                ],
                stdout=output,
            )

            self.assertEqual(exit_code, 0)
            self.assertIn('"metric": "retention_rate"', output.getvalue())

    def test_cli_metric_override_selects_the_requested_metric(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(
                [
                    "--config",
                    str(Path(directory) / "config.json"),
                    "analyze",
                    "--question",
                    "What changed?",
                    "--metric",
                    "retention_rate",
                ],
                stdout=output,
            )

            self.assertEqual(exit_code, 0)
            self.assertIn('"metric": "retention_rate"', output.getvalue())

    def test_report_writes_a_standalone_task_html_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            WorkspaceStore(root / "workbench.sqlite3").save_task(
                AnalysisTask.create("task-report", "渠道增长复盘", "解释收入与留存的变化")
            )
            report_path = root / "exports" / "decision-brief.html"
            output = StringIO()

            exit_code = main(
                [
                    "--config",
                    str(config_path),
                    "report",
                    "--task",
                    "task-report",
                    "--output",
                    str(report_path),
                ],
                stdout=output,
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(report_path.is_file())
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("渠道增长复盘", html)
            self.assertIn("Content-Security-Policy", html)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["task_id"], "task-report")
            self.assertEqual(payload["output"], str(report_path.resolve()))
            self.assertEqual(len(payload["sha256"]), 64)

    def test_one_business_command_creates_the_task_and_exports_a_complete_report(self):
        root = Path(__file__).resolve().parents[1]
        case = root / "src" / "data2doc2data" / "sample" / "cases" / "retail-promotion-fulfillment"
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "management-review.html"
            output = StringIO()

            exit_code = main(
                [
                    "--config", str(Path(directory) / "config.json"),
                    "analyze-case", "--question", "大促增长是否损害利润和履约？",
                    "--source", str(case), "--output", str(destination),
                ],
                stdout=output,
            )

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["source_summary"]["record_count"], 260)
            self.assertEqual(payload["rule_verdicts"]["confirmed_count"], 3)
            self.assertEqual(payload["report"]["output"], str(destination.resolve()))
            self.assertIn("promotion-margin-conflict", destination.read_text(encoding="utf-8"))

    def test_cli_runs_lists_and_reports_a_model_free_cycle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            data = root / "metrics.csv"
            data.write_text(
                "date,metric,value\n"
                + "".join(f"2026-01-{index:02d},gmv,{value}\n" for index, value in enumerate([10, 10, 11, 10, 50, 20, 20, 21], 1)),
                encoding="utf-8",
            )
            snapshot = SnapshotRef("dataset", "dataset-cli-cycle", hashlib.sha256(data.read_bytes()).hexdigest())
            workspace = WorkspaceStore(root / "workbench.sqlite3")
            workspace.save_task(AnalysisTask.create("task-cli-cycle", "循环复盘", "解释异常", (snapshot,)))
            output = StringIO()

            exit_code = main(
                ["--config", str(config_path), "cycle-run", "--task", "task-cli-cycle", "--data", str(data)],
                stdout=output,
            )
            cycle_id = json.loads(output.getvalue())["cycle"]["cycle_id"]
            artifacts_output = StringIO()
            main(["--config", str(config_path), "cycle-artifacts", "--cycle", cycle_id], stdout=artifacts_output)
            report_path = root / "cycle-report.html"
            report_output = StringIO()
            report_exit = main(
                ["--config", str(config_path), "cycle-report", "--cycle", cycle_id, "--output", str(report_path)],
                stdout=report_output,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(report_exit, 0)
            self.assertTrue(json.loads(artifacts_output.getvalue())["artifact_refs"])
            self.assertIn("分析方法、产物与限制", report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
