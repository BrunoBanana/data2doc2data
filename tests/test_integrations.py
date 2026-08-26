from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from data2doc2data.cli import main
from data2doc2data.config import ProfileStore
from data2doc2data.integrations import load_host_templates, run_doctor, validate_host_templates


ROOT = Path(__file__).resolve().parents[1]


class IntegrationTests(unittest.TestCase):
    def test_native_codex_and_workbuddy_plugins_bundle_the_same_agent_skill(self):
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        workbuddy = json.loads((ROOT / ".codebuddy-plugin" / "plugin.json").read_text(encoding="utf-8"))
        server = codex["mcpServers"]["data2doc2data"]
        skill = (ROOT / "skills" / "data2doc2data" / "SKILL.md").read_text(encoding="utf-8")

        self.assertEqual(codex["name"], "data2doc2data")
        self.assertEqual(codex["skills"], "./skills/")
        self.assertEqual(workbuddy["name"], "data2doc2data")
        self.assertIn("${CODEBUDDY_PLUGIN_ROOT}/scripts/plugin_mcp.py", workbuddy["mcpServers"]["data2doc2data"]["args"])
        self.assertEqual(server["command"], "python3")
        self.assertEqual(server["args"], ["./scripts/plugin_mcp.py"])
        self.assertFalse((ROOT / ".mcp.json").exists(), "project MCP must not shadow a trusted user installation")
        self.assertIn("analyze_business_case", skill)
        self.assertIn("task_id", skill)

    def test_native_plugin_launcher_prefers_the_projects_executable_virtual_environment(self):
        specification = importlib.util.spec_from_file_location("data2doc2data_plugin_launcher", ROOT / "scripts" / "plugin_mcp.py")
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        launcher = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(launcher)

        with patch.object(launcher.os, "execv", side_effect=RuntimeError("intercepted")) as execute:
            with self.assertRaisesRegex(RuntimeError, "intercepted"):
                launcher.main()

        executable = str(ROOT / ".venv" / "bin" / "data2doc2data")
        execute.assert_called_once_with(executable, [executable, "mcp"])

    def test_native_plugin_launcher_rejects_non_executable_or_missing_local_runtime(self):
        specification = importlib.util.spec_from_file_location("data2doc2data_plugin_launcher_missing", ROOT / "scripts" / "plugin_mcp.py")
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        launcher = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(launcher)
        output = StringIO()

        with (
            patch.object(launcher.Path, "is_file", return_value=True),
            patch.object(launcher.os, "access", return_value=False),
            patch.object(launcher.importlib.util, "find_spec", return_value=None),
            patch.object(launcher.os, "execv") as execute,
            redirect_stderr(output),
        ):
            result = launcher.main()

        self.assertEqual(result, 1)
        execute.assert_not_called()
        self.assertIn("python3 -m venv .venv", output.getvalue())

    def test_native_plugin_launcher_can_use_the_current_installed_python(self):
        specification = importlib.util.spec_from_file_location("data2doc2data_plugin_launcher_python", ROOT / "scripts" / "plugin_mcp.py")
        self.assertIsNotNone(specification)
        self.assertIsNotNone(specification.loader)
        launcher = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(launcher)

        with (
            patch.object(launcher.Path, "is_file", return_value=False),
            patch.object(launcher.importlib.util, "find_spec", return_value=object()),
            patch.object(launcher.os, "execv", side_effect=RuntimeError("intercepted")) as execute,
        ):
            with self.assertRaisesRegex(RuntimeError, "intercepted"):
                launcher.main()

        execute.assert_called_once_with(
            sys.executable,
            [sys.executable, "-m", "data2doc2data.cli", "mcp"],
        )

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
        self.assertGreaterEqual(checks["mcp_protocol"]["tool_count"], 15)
        self.assertIn("generate_html_report", checks["mcp_protocol"]["tools"])
        self.assertIn("run_analysis_cycle", checks["mcp_protocol"]["tools"])
        self.assertIn("generate_cycle_html_report", checks["mcp_protocol"]["tools"])
        self.assertIn("create_analysis_task", checks["mcp_protocol"]["tools"])
        self.assertIn("evaluate_task_rules", checks["mcp_protocol"]["tools"])
        self.assertIn("analyze_business_case", checks["mcp_protocol"]["tools"])
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

    def test_one_step_host_installation_can_be_inspected_without_mutating_the_host(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(
                [
                    "--config",
                    str(Path(directory) / "config.json"),
                    "install-mcp",
                    "--host",
                    "codebuddy",
                    "--scope",
                    "user",
                    "--dry-run",
                ],
                stdout=output,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["host"], "codebuddy")
        self.assertEqual(payload["status"], "dry_run")
        self.assertEqual(payload["command"][:5], ["codebuddy", "mcp", "add", "--scope", "user"])
        self.assertEqual(payload["command"][-2], str(Path(sys.executable).parent / "data2doc2data"))
        self.assertEqual(payload["command"][-1], "mcp")

    def test_workbuddy_product_name_is_accepted_as_a_codebuddy_host_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            exit_code = main(
                ["--config", str(Path(directory) / "config.json"), "install-mcp", "--host", "workbuddy", "--dry-run"],
                stdout=output,
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["host"], "workbuddy")
        self.assertEqual(payload["command"][0], "codebuddy")


if __name__ == "__main__":
    unittest.main()
