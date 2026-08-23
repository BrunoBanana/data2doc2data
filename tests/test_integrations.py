from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

from data2doc2data.cli import main
from data2doc2data.config import ProfileStore
from data2doc2data.integrations import load_host_templates, run_doctor, validate_host_templates


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_host_templates_launch_the_same_local_mcp_server_without_secrets(self):
        templates = load_host_templates()

        self.assertEqual(set(templates), {"codex", "deepseek-harness", "codebuddy"})
        codex = tomllib.loads(templates["codex"])
        self.assertEqual(codex["mcp_servers"]["data2doc2data"]["command"], "data2doc2data")
        self.assertEqual(codex["mcp_servers"]["data2doc2data"]["args"], ["mcp"])
        codebuddy = json.loads(templates["codebuddy"])
        self.assertEqual(codebuddy["mcpServers"]["data2doc2data"]["type"], "stdio")
        self.assertEqual(codebuddy["mcpServers"]["data2doc2data"]["args"], ["mcp"])
        self.assertIn("name: '@deepseek-ai/dsh-mcp-client'", templates["deepseek-harness"])
        self.assertIn("serverName: data2doc2data", templates["deepseek-harness"])
        self.assertIn("args: ['mcp']", templates["deepseek-harness"])
        for text in templates.values():
            self.assertNotIn("API_KEY", text)
            self.assertNotIn("/Users/", text)
            self.assertNotIn("Bearer ", text)
        self.assertTrue(validate_host_templates(templates))

    def test_checked_in_examples_match_the_packaged_templates(self):
        expected = {
            "codex": ROOT / "integrations" / "codex" / "config.toml.example",
            "deepseek-harness": ROOT / "integrations" / "deepseek-harness" / "data2doc2data.cordis.yml.example",
            "codebuddy": ROOT / "integrations" / "codebuddy" / ".mcp.json.example",
        }
        for host, path in expected.items():
            self.assertEqual(path.read_text(encoding="utf-8"), load_host_templates()[host])

    def test_doctor_exercises_cases_mcp_tools_and_templates_without_spawning_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "config.json")
            report = run_doctor(store)

        self.assertTrue(report["ok"])
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["flagship_cases"]["case_count"], 2)
        self.assertEqual(checks["mcp_protocol"]["tool_count"], 3)
        self.assertGreater(checks["source_profile"]["record_count"], 0)
        self.assertEqual(checks["host_templates"]["host_count"], 3)
        self.assertNotIn("/Users/", json.dumps(report))

    def test_doctor_cli_has_machine_readable_exit_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(
                ["--config", str(Path(directory) / "config.json"), "doctor", "--json"],
                stdout=output,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["product"], "data2doc2data")


if __name__ == "__main__":
    unittest.main()
