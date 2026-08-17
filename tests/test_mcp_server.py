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

    def test_tools_list_exposes_the_three_evidence_tools(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, store)

        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertEqual(names, TOOL_NAMES)
        self.assertEqual(TOOL_NAMES, {"analyze", "check_rules", "source_profile"})
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
        self.assertEqual(len(response["result"]["tools"]), 3)

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
