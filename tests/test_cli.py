from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.cli import main
from data2doc2data.workspace import AnalysisTask
from data2doc2data.workspace_store import WorkspaceStore


class CliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
