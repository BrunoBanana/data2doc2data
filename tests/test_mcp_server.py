import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from data2doc2data.config import Profile, ProfileStore
from data2doc2data.mcp_server import (
    PROTOCOL_VERSION,
    TOOL_NAMES,
    handle_message,
    serve,
)
from data2doc2data.workspace import AnalysisTask
from data2doc2data.workspace_store import WorkspaceStore


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "src" / "data2doc2data" / "sample" / "cases"


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
                "inspect_sources",
                "create_analysis_task",
                "analyze_task_metric",
                "evaluate_task_rules",
                "run_diagnostic_step",
                "get_analysis_trace",
                "resume_analysis_cycle",
                "analyze_business_case",
            },
        )
        for tool in response["result"]["tools"]:
            self.assertTrue(tool["description"])
            self.assertIn("type", tool["inputSchema"])

    def test_tools_list_declares_safe_local_permission_hints(self):
        store, tmp = make_store()
        self.addCleanup(tmp.cleanup)
        response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, store)
        tools = {tool["name"]: tool for tool in response["result"]["tools"]}

        for name, tool in tools.items():
            with self.subTest(tool=name):
                self.assertFalse(tool["annotations"]["destructiveHint"])
                self.assertFalse(tool["annotations"]["openWorldHint"])

        self.assertTrue(tools["inspect_sources"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["get_analysis_trace"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["create_analysis_task"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["analyze_business_case"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["run_diagnostic_step"]["annotations"]["idempotentHint"])

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


class McpBusinessWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.store, temporary = make_store()
        self.addCleanup(temporary.cleanup)
        self.retail = CASES / "retail-promotion-fulfillment"
        self.saas = CASES / "saas-growth-retention"

    def call(self, name, arguments):
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            self.store,
        )
        self.assertNotIn("error", response, response)
        self.assertNotEqual(response["result"].get("isError"), True, response)
        return json.loads(response["result"]["content"][0]["text"]), response["result"]

    def create_retail_task(self):
        payload, _ = self.call(
            "create_analysis_task",
            {
                "question": "大促增长是否以毛利、履约和复购为代价？",
                "paths": [str(self.retail)],
            },
        )
        return payload

    def test_inspect_sources_discovers_directory_materials_without_paths_or_rows(self):
        payload, result = self.call("inspect_sources", {"paths": [str(self.retail)]})

        self.assertEqual(payload["dataset_count"], 1)
        self.assertEqual(payload["document_count"], 5)
        self.assertEqual(payload["row_count"], 260)
        self.assertEqual(payload["modalities"], ["data", "text"])
        self.assertNotIn(str(self.retail), result["content"][0]["text"])
        self.assertNotIn("sample_rows", result["content"][0]["text"])

    def test_create_analysis_task_locks_sources_without_mutating_global_profile(self):
        self.store.save(Profile.demo())
        before = self.store.path.read_bytes()

        payload = self.create_retail_task()

        self.assertTrue(payload["task_id"].startswith("task-"))
        self.assertEqual(payload["source_summary"]["record_count"], 260)
        self.assertEqual(payload["source_summary"]["document_count"], 5)
        task = WorkspaceStore(self.store.workspace_database_path).get_task(payload["task_id"])
        self.assertEqual(len(task.snapshot_refs), 6)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_host_case_analysis_does_not_receive_hidden_demo_answers_or_seeded_hypotheses(self):
        payload = self.create_retail_task()

        hidden = WorkspaceStore(self.store.workspace_database_path).get_task_artifact(
            payload["task_id"], "flagship_case"
        )

        self.assertIsNone(hidden)

    def test_one_html_review_can_become_both_a_dataset_and_a_document(self):
        report = self.store.path.parent / "quarterly-review.html"
        report.write_text(
            "<html><body><h1>季度复盘</h1><p>毛利率下降需要进一步验证。</p>"
            "<table><tr><th>date</th><th>metric</th><th>value</th></tr>"
            "<tr><td>2026-01-01</td><td>gross_margin_rate</td><td>0.36</td></tr>"
            "<tr><td>2026-01-08</td><td>gross_margin_rate</td><td>0.31</td></tr>"
            "</table></body></html>",
            encoding="utf-8",
        )

        created, _ = self.call(
            "create_analysis_task",
            {"question": "毛利率为什么下降？", "paths": [str(report)]},
        )
        finding, _ = self.call(
            "analyze_task_metric",
            {"task_id": created["task_id"], "question": "毛利率为什么下降？", "metric": "gross_margin_rate"},
        )

        self.assertEqual(created["source_summary"]["record_count"], 2)
        self.assertEqual(created["source_summary"]["document_count"], 1)
        self.assertEqual(finding["signal"]["direction"], "down")

    def test_task_metric_analysis_is_isolated_and_has_compact_provenance(self):
        self.store.save(Profile.demo())
        before = self.store.path.read_bytes()
        retail = self.create_retail_task()
        saas, _ = self.call(
            "create_analysis_task",
            {"question": "增长与留存为什么背离？", "paths": [str(self.saas)]},
        )

        retail_result, retail_response = self.call(
            "analyze_task_metric",
            {"task_id": retail["task_id"], "question": "毛利率为什么下降？", "metric": "gross_margin_rate"},
        )
        saas_result, _ = self.call(
            "analyze_task_metric",
            {"task_id": saas["task_id"], "question": "留存为什么下降？", "metric": "retention_8w"},
        )

        self.assertEqual(retail_result["signal"]["metric"], "gross_margin_rate")
        self.assertEqual(saas_result["signal"]["metric"], "retention_8w")
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertNotIn(str(self.retail), retail_response["content"][0]["text"])
        self.assertLess(len(retail_response["content"][0]["text"].encode("utf-8")), 8_192)
        for source in retail_result["provenance"]["sources"]:
            self.assertNotIn("path", source)
            self.assertNotIn("rows", source)

    def test_evaluate_task_rules_executes_every_clause_against_locked_data(self):
        task = self.create_retail_task()

        payload, _ = self.call("evaluate_task_rules", {"task_id": task["task_id"]})

        self.assertEqual(payload["rule_count"], 3)
        self.assertEqual(payload["confirmed_count"], 3)
        self.assertEqual({item["status"] for item in payload["results"]}, {"confirmed"})
        for rule in payload["results"]:
            self.assertTrue(rule["clauses"])
            self.assertTrue(all("observed_direction" in clause for clause in rule["clauses"]))

    def test_host_can_choose_local_diagnostic_steps_without_receiving_raw_rows(self):
        task = self.create_retail_task()

        payload, result = self.call(
            "run_diagnostic_step",
            {
                "task_id": task["task_id"],
                "tool": "detect_anomalies",
                "arguments": {"metric": "stockout_rate", "window": 5, "threshold": 4.0},
            },
        )

        self.assertEqual(payload["tool"], "detect_anomalies")
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["artifact_refs"])
        self.assertNotIn(str(self.retail), result["content"][0]["text"])

    def test_cycle_can_infer_locked_sources_and_reports_share_completed_run_state(self):
        task = self.create_retail_task()

        cycle, _ = self.call("run_analysis_cycle", {"task_id": task["task_id"]})
        trace, _ = self.call("get_analysis_trace", {"task_id": task["task_id"]})
        report, response = self.call("generate_html_report", {"task_id": task["task_id"]})
        cycle_report, cycle_response = self.call(
            "generate_cycle_html_report", {"cycle_id": cycle["cycle"]["cycle_id"]}
        )

        self.assertEqual(cycle["cycle"]["status"], "completed")
        self.assertGreater(trace["run_count"], 0)
        self.assertGreater(trace["event_count"], 0)
        self.assertGreater(len(trace["artifact_refs"]), 0)
        self.assertEqual(len(report["sha256"]), 64)
        self.assertEqual(len(cycle_report["sha256"]), 64)
        for resource in (response["content"][1], cycle_response["content"][1]):
            html = Path(resource["uri"].removeprefix("file://")).read_text(encoding="utf-8")
            self.assertIn("260", html)
            self.assertIn("detect_anomalies", html)
            self.assertIn("通信与恢复审计", html)
            self.assertNotIn("尚无可量化结论", html)
            self.assertNotIn("当前任务尚未接入可分析的数据快照", html)
            self.assertNotIn("文本材料尚未纳入", html)
            self.assertNotIn("尚未生成多轮诊断产物", html)

    def test_one_business_request_creates_analyzes_verifies_and_exports_report(self):
        self.store.save(Profile.demo())
        before = self.store.path.read_bytes()

        payload, response = self.call(
            "analyze_business_case",
            {
                "question": "大促增长是否以利润、履约和复购为代价？",
                "paths": [str(self.retail)],
                "filename": "retail-decision.html",
            },
        )

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source_summary"]["record_count"], 260)
        self.assertEqual(payload["source_summary"]["document_count"], 5)
        self.assertEqual(payload["rule_verdicts"]["confirmed_count"], 3)
        self.assertEqual(len(payload["metric_findings"]), 10)
        self.assertEqual(len(payload["report"]["sha256"]), 64)
        self.assertEqual(response["content"][1]["type"], "resource_link")
        html = Path(response["content"][1]["uri"].removeprefix("file://")).read_text(encoding="utf-8")
        self.assertIn("gross_margin_rate", html)
        self.assertIn("promotion-margin-conflict", html)
        self.assertIn("证据", html)
        self.assertNotIn(str(self.retail), html)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_data_only_business_request_reports_missing_text_and_rules_honestly(self):
        dataset = self.store.path.parent / "metrics.csv"
        dataset.write_text(
            "date,metric,value\n"
            + "".join(f"2026-01-{index:02d},revenue,{100 + index * 10}\n" for index in range(1, 9)),
            encoding="utf-8",
        )

        payload, response = self.call(
            "analyze_business_case",
            {"question": "收入发生了什么变化？", "paths": [str(dataset)]},
        )

        self.assertEqual(payload["source_summary"]["document_count"], 0)
        self.assertEqual(payload["rule_verdicts"]["rule_count"], 0)
        self.assertEqual(payload["metric_findings"][0]["signal"]["direction"], "up")
        report = Path(response["content"][1]["uri"].removeprefix("file://")).read_text(encoding="utf-8")
        self.assertIn("文本材料尚未纳入", report)


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
        self.assertEqual(len(response["result"]["tools"]), len(TOOL_NAMES))

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
