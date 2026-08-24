import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from data2doc2data.config import ProfileStore
from data2doc2data.mcp_server import (
    PROTOCOL_VERSION,
    TOOL_NAMES,
    handle_message,
    serve,
)
from data2doc2data.workspace import AnalysisTask
from data2doc2data.workspace_store import WorkspaceStore


def make_store():
    tmp = tempfile.TemporaryDirectory()
    store = ProfileStore(Path(tmp.name) / "config.json")
    return store, tmp


class McpProtocolTests(unittest.TestCase):
    def test_initialize_negotiates_tools_capability(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL_VERSION}},
            store,
        )

        self.assertEqual(response["result"]["protocolVersion"], PROTOCOL_VERSION)
        self.assertEqual(response["result"]["capabilities"], {"tools": {"listChanged": False}})
        self.assertEqual(response["result"]["serverInfo"]["name"], "data2doc2data")

    def test_tools_list_exposes_evidence_and_report_tools(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, store)

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(names, TOOL_NAMES)
        self.assertEqual(
            TOOL_NAMES,
            {
                "analyze",
                "check_rules",
                "source_profile",
                "generate_html_report",
                "run_analysis_cycle",
                "list_cycle_artifacts",
                "generate_cycle_html_report",
            },
        )
        for tool in response["result"]["tools"]:
            self.assertTrue(tool["description"])
            self.assertIn("type", tool["inputSchema"])

    def test_unknown_method_returns_method_not_found(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "bogus/method"}, store)

        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool_returns_invalid_params(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "nope"}},
            store,
        )

        self.assertEqual(response["error"]["code"], -32602)

    def test_notification_is_not_answered(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        self.assertIsNone(handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, store))

    def test_missing_question_is_a_protocol_error(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "analyze", "arguments": {}}},
            store,
        )

        self.assertEqual(response["error"]["code"], -32602)


class McpToolTests(unittest.TestCase):
    def test_analyze_tool_returns_deterministic_evidence_for_demo(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "analyze", "arguments": {"question": "留存为什么下降？"}},
            },
            store,
        )

        result = response["result"]
        self.assertNotEqual(result.get("isError"), True)
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["signal"]["metric"], "retention_rate")
        self.assertIn("validation", payload)
        self.assertIn("verification", payload)

    def test_analyze_tool_reports_business_errors_as_is_error(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "analyze",
                    "arguments": {"question": "What changed?", "metric": "missing_metric"},
                },
            },
            store,
        )

        result = response["result"]
        self.assertEqual(result.get("isError"), True)
        self.assertIn("is not available", result["content"][0]["text"])

    def test_check_rules_tool_lists_metrics_and_rules(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write(
                json.dumps(
                    {
                        "version": 1,
                        "metrics": {"revenue": {"aliases": ["收入"]}},
                        "rules": [
                            {
                                "id": "r1",
                                "name": "收入规则",
                                "clauses": [{"metric": "revenue", "direction": "up"}],
                            }
                        ],
                    }
                )
            )
            rules_path = handle.name
        self.addCleanup(lambda: Path(rules_path).unlink(missing_ok=True))

        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "check_rules", "arguments": {"rules_path": rules_path}},
            },
            store,
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertTrue(payload["valid"])
        self.assertEqual(payload["metrics"], ["revenue"])
        self.assertEqual(payload["rules"], ["r1"])

    def test_source_profile_tool_returns_counts_without_raw_rows(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "source_profile", "arguments": {}}},
            store,
        )

        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["record_count"], 12)
        self.assertEqual(payload["metrics"], ["activation_rate", "retention_rate"])
        text = response["result"]["content"][0]["text"]
        self.assertNotIn("0.66", text)

    def test_generate_html_report_returns_metadata_and_a_local_resource_link(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        WorkspaceStore(store.workspace_database_path).save_task(
            AnalysisTask.create("task-report", "利润与履约复盘", "判断促销是否值得延续")
        )

        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "generate_html_report",
                    "arguments": {"task_id": "task-report", "filename": "利润 report.html"},
                },
            },
            store,
        )

        result = response["result"]
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual(payload["task_id"], "task-report")
        self.assertEqual(payload["mime_type"], "text/html; charset=utf-8")
        self.assertEqual(len(payload["sha256"]), 64)
        resource = result["content"][1]
        self.assertEqual(resource["type"], "resource_link")
        self.assertEqual(resource["mimeType"], "text/html")
        self.assertTrue(resource["uri"].startswith("file://"))
        report_path = Path(resource["uri"].removeprefix("file://"))
        self.assertEqual(report_path.parent, (store.path.parent / "reports").resolve())
        self.assertEqual(report_path.name, "report.html")
        self.assertIn("利润与履约复盘", report_path.read_text(encoding="utf-8"))

    def test_mcp_runs_and_reports_the_same_local_cycle_contract(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        data = root / "metrics.csv"
        data.write_text(
            "date,metric,value\n"
            + "".join(f"2026-01-{index:02d},gmv,{value}\n" for index, value in enumerate([10, 10, 11, 10, 50, 20, 20, 21], 1)),
            encoding="utf-8",
        )
        import hashlib

        from data2doc2data.workspace import SnapshotRef

        snapshot = SnapshotRef("dataset", "dataset-mcp-cycle", hashlib.sha256(data.read_bytes()).hexdigest())
        WorkspaceStore(store.workspace_database_path).save_task(
            AnalysisTask.create("task-mcp-cycle", "MCP 循环", "解释异常", (snapshot,))
        )

        run = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "run_analysis_cycle",
                    "arguments": {"task_id": "task-mcp-cycle", "data_path": str(data)},
                },
            },
            store,
        )
        cycle_id = json.loads(run["result"]["content"][0]["text"])["cycle"]["cycle_id"]
        report = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "generate_cycle_html_report", "arguments": {"cycle_id": cycle_id}},
            },
            store,
        )

        self.assertNotEqual(run["result"].get("isError"), True)
        self.assertEqual(report["result"]["content"][1]["type"], "resource_link")
        self.assertNotIn(str(data), run["result"]["content"][0]["text"])


class McpServeTests(unittest.TestCase):
    def test_serve_processes_a_stream_and_emits_newline_json(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        stdin = StringIO('{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
        stdout = StringIO()

        serve(store, stdin=stdin, stdout=stdout)

        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        response = json.loads(lines[0])
        self.assertEqual(response["id"], 1)
        self.assertEqual(len(response["result"]["tools"]), 7)

    def test_serve_skips_invalid_json_with_a_parse_error(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        stdin = StringIO("not-json\n")
        stdout = StringIO()

        serve(store, stdin=stdin, stdout=stdout)

        response = json.loads(stdout.getvalue().strip())
        self.assertEqual(response["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
