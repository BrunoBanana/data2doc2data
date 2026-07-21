from io import StringIO
from pathlib import Path
import tempfile
import unittest

from data2doc2data.cli import main


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


if __name__ == "__main__":
    unittest.main()
