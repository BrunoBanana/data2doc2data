from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
from data2doc2data.artifacts import ArtifactStore
from data2doc2data.diagnostics import AnalyticalArtifact
from data2doc2data.reporting import build_html_report, build_html_report_from_cycle
from data2doc2data.workspace import AnalysisTask, SnapshotRef


class _Parser(HTMLParser):
    def error(self, message):  # pragma: no cover - compatibility hook
        raise AssertionError(message)


class ReportingTests(unittest.TestCase):
    def test_report_renders_an_escaped_protocol_audit_from_persisted_events(self):
        task = AnalysisTask.create("task-protocol", "协议复盘", "检查 Agent Flow 可追踪性")
        run_events = [
            {
                "kind": "tool.started",
                "artifact_refs": ["artifact-1"],
                "communication": {
                    "trace_id": "run-protocol",
                    "message_id": "msg-1",
                    "sender": "<agent>",
                    "receiver": "tool.profile_data",
                    "attempt": 2,
                    "idempotency_key": "delivery-abc",
                    "deadline_at": "2026-08-26T08:00:00Z",
                },
            },
            {
                "kind": "cycle.checkpointed",
                "artifact_refs": [],
                "communication": {
                    "trace_id": "run-protocol",
                    "message_id": "msg-2",
                    "sender": "orchestrator",
                    "receiver": "evidence_store",
                    "attempt": 1,
                    "idempotency_key": "delivery-def",
                    "deadline_at": None,
                },
            },
        ]

        report = build_html_report(task, None, None, None, run_count=1, run_events=run_events)

        self.assertIn("通信与恢复审计", report.html)
        self.assertIn("TRACE run-protocol", report.html)
        self.assertIn("&lt;agent&gt; → tool.profile_data", report.html)
        self.assertIn("最大尝试 2", report.html)
        self.assertIn("检查点 1", report.html)
        self.assertNotIn("<agent>", report.html)

    def test_report_is_answer_first_self_contained_and_escaped(self):
        task = AnalysisTask.create(
            "task-1",
            "收入 <script>alert(1)</script> 复盘",
            "解释收入变化并决定下一步",
            (SnapshotRef("dataset", "dataset-1", "a" * 64),),
        )
        dashboard = {
            "contract_version": 1,
            "dashboard_id": "dashboard-1",
            "title": "数据概览",
            "blocks": [
                {"block_id": "records", "kind": "kpi", "title": "记录数", "value": 12, "data": [], "provenance": {"snapshot_id": "dataset-1", "sha256": "a" * 64, "expression": "count rows", "fields": ["date"], "result_row_count": 1}},
                {"block_id": "trend", "kind": "chart", "title": "收入趋势", "value": None, "chart": {"mark": "line", "encoding": {"x": {"field": "date", "type": "temporal"}, "y": {"field": "value", "type": "quantitative"}, "color": {"field": "metric", "type": "nominal"}}, "transforms": []}, "data": [{"date": "2026-01", "metric": "收入", "value": 10}, {"date": "2026-02", "metric": "收入", "value": 12}], "provenance": {"snapshot_id": "dataset-1", "sha256": "a" * 64, "expression": "average value by date", "fields": ["date", "value"], "result_row_count": 2}},
            ],
        }
        text = {"corpus_id": "corpus-1", "document_count": 1, "failure_count": 0, "duplicate_count": 0, "topics": ["收入"], "entities": ["华东区"], "claims": [{"claim_id": "claim-1", "text": "收入将增长", "status": "pending", "citation": {"document": "strategy.md", "sha256": "b" * 64, "start_line": 2, "end_line": 2, "excerpt": "主张：收入将增长"}, "conflicts_with": []}]}
        graph = {
            "contract_version": 1,
            "graph_id": "graph-1",
            "nodes": [
                {"node_id": "signal-1", "kind": "data_signal", "label": "收入下降 8%", "status": "verified", "artifact_ref": "dashboard-1"},
                {"node_id": "hypothesis-1", "kind": "hypothesis", "label": "价格影响收入", "status": "supported", "artifact_ref": None},
                {"node_id": "validation-1", "kind": "validation", "label": "收入方向符合假设", "status": "supported", "artifact_ref": "validation-1"},
                {"node_id": "hypothesis-2", "kind": "hypothesis", "label": "渠道结构没有变化", "status": "contradicted", "artifact_ref": None},
                {"node_id": "validation-2", "kind": "validation", "label": "渠道变化反驳该假设", "status": "contradicted", "artifact_ref": "validation-2"},
                {"node_id": "hypothesis-3", "kind": "hypothesis", "label": "仓库延迟导致退款", "status": "insufficient", "artifact_ref": None},
                {"node_id": "validation-3", "kind": "validation", "label": "缺少仓库维度", "status": "insufficient", "artifact_ref": None},
                {"node_id": "conclusion-1", "kind": "conclusion", "label": "一项支持、一项冲突、一项待补证", "status": "supported", "artifact_ref": "graph-1"},
                {"node_id": "action-1", "kind": "action", "label": "补充仓库和渠道明细后重新运行", "status": "pending", "artifact_ref": "graph-1"},
            ],
            "edges": [
                {"edge_id": "edge-1", "source": "validation-1", "target": "hypothesis-1", "relationship": "tests"},
                {"edge_id": "edge-2", "source": "signal-1", "target": "validation-1", "relationship": "supports"},
                {"edge_id": "edge-3", "source": "validation-2", "target": "hypothesis-2", "relationship": "tests"},
                {"edge_id": "edge-4", "source": "signal-1", "target": "validation-2", "relationship": "contradicts"},
                {"edge_id": "edge-5", "source": "validation-3", "target": "hypothesis-3", "relationship": "tests"},
                {"edge_id": "edge-6", "source": "signal-1", "target": "validation-3", "relationship": "insufficient_for"},
                {"edge_id": "edge-7", "source": "conclusion-1", "target": "action-1", "relationship": "derived_from"},
            ],
        }

        diagnostic = {
            "blocks": [{
                "block_id": "block-anomaly", "kind": "anomalies", "title": "检测到 1 个异常点", "status": "completed",
                "provenance": {"artifact_ref": "artifact-anomaly", "method": "detect_anomalies", "sample_size": 26, "limitations": ["异常不代表因果。"]},
                "observations": {"anomaly_count": 1, "change_percent": -11.1, "anomalies": [{"date": "2026-05-01", "value": 50, "robust_score": 4.2}]},
            }],
        }

        artifact = build_html_report(task, dashboard, text, graph, run_count=1, artifact_dashboard=diagnostic)

        self.assertTrue(artifact.filename.endswith(".html"))
        self.assertIn("<h2>分析结论</h2>", artifact.html)
        self.assertLess(artifact.html.index("分析结论"), artifact.html.index("关键发现"))
        self.assertIn("证据验证", artifact.html)
        self.assertIn("假设生成与验证树", artifact.html)
        self.assertIn("解释收入变化并决定下一步", artifact.html)
        self.assertIn("价格影响收入", artifact.html)
        self.assertIn("收入方向符合假设", artifact.html)
        self.assertIn("获得支持", artifact.html)
        self.assertIn("存在冲突", artifact.html)
        self.assertIn("证据不足", artifact.html)
        self.assertIn("补充仓库和渠道明细后重新运行", artifact.html)
        self.assertIn("只展示公开决策摘要、确定性工具结果和显式证据关系", artifact.html)
        self.assertIn('class="hypothesis-tree-report"', artifact.html)
        self.assertIn("<span>已验证</span><strong>4</strong>", artifact.html)
        self.assertIn("<span>待验证</span><strong>3</strong>", artifact.html)
        self.assertIn("证据不足 2", artifact.html)
        self.assertNotIn("insufficient 1", artifact.html)
        self.assertIn("--paper:#f4f1e8", artifact.html)
        self.assertIn("--signal:#08d36c", artifact.html)
        self.assertIn("--ink:#151511", artifact.html)
        self.assertIn("box-shadow:4px 4px 0", artifact.html)
        self.assertIn("<svg", artifact.html)
        self.assertIn("推荐下一步", artifact.html)
        self.assertIn("仍需回答的问题", artifact.html)
        self.assertIn("局限与假设", artifact.html)
        self.assertIn("深度诊断产物", artifact.html)
        self.assertIn("detect_anomalies", artifact.html)
        self.assertIn("2026-05-01", artifact.html)
        self.assertIn("异常不代表因果", artifact.html)
        self.assertIn("dataset-1", artifact.html)
        self.assertIn("count rows", artifact.html)
        self.assertIn("strategy.md · 第 2–2 行", artifact.html)
        self.assertNotIn("<script>alert(1)</script>", artifact.html)
        self.assertIn("收入 &lt;script&gt;alert(1)&lt;/script&gt; 复盘", artifact.html)
        self.assertNotIn("src=\"http", artifact.html)
        self.assertNotIn("href=\"http", artifact.html)
        self.assertNotIn("<script", artifact.html)
        self.assertIn("@media print", artifact.html)
        _Parser().feed(artifact.html)

    def test_report_does_not_include_local_paths_or_unbounded_raw_rows(self):
        task = AnalysisTask.create("task-1", "复盘", "解释变化")
        artifact = build_html_report(task, None, None, None, run_count=0)
        self.assertNotIn("/Users/", artifact.html)
        self.assertNotIn("sample_rows", artifact.html)
        self.assertIn("当前任务尚未接入可分析的数据快照", artifact.html)

    def test_business_report_formats_units_thresholds_and_verdicts_for_decision_makers(self):
        task = AnalysisTask.create("task-business-report", "经营复盘", "判断毛利变化")
        findings = {
            "metric_findings": [
                {
                    "metric": "gross_margin_rate",
                    "signal": {
                        "baseline": 0.357,
                        "current": 0.3035769230769231,
                        "direction": "down",
                        "spec": {"unit": "ratio", "threshold": 0.005},
                    },
                    "validation": {"status": "supported"},
                },
                {
                    "metric": "gmv",
                    "signal": {
                        "baseline": 4_180_000.0,
                        "current": 5_231_538.461538462,
                        "direction": "up",
                        "spec": {"unit": "CNY", "threshold": 10_000},
                    },
                    "validation": {"status": "mixed"},
                },
            ],
            "rule_verdicts": {
                "rule_count": 1,
                "confirmed_count": 1,
                "contradicted_count": 0,
                "unavailable_count": 0,
                "results": [
                    {
                        "rule_id": "margin-rule",
                        "name": "毛利恶化",
                        "status": "confirmed",
                        "clauses": [
                            {
                                "metric": "gross_margin_rate",
                                "expected_direction": "down",
                                "observed_direction": "down",
                                "status": "confirmed",
                            }
                        ],
                    }
                ],
            },
        }

        report = build_html_report(task, None, None, None, run_count=1, business_findings=findings)

        self.assertIn("35.70%", report.html)
        self.assertIn("30.36%", report.html)
        self.assertIn("0.50 个百分点", report.html)
        self.assertIn("4,180,000", report.html)
        self.assertIn("10,000 CNY", report.html)
        self.assertIn("实证状态 数据支持", report.html)
        self.assertIn("<td>下降</td>", report.html)
        self.assertNotIn("0.3035769230769231", report.html)
        self.assertNotIn("尚无可量化结论", report.html)

    def test_cycle_report_contains_methods_limits_and_no_external_assets(self):
        task = AnalysisTask.create("task-cycle-report", "异常复盘", "解释 GMV 异常")
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            artifact = AnalyticalArtifact(
                "artifact-report",
                "detect_anomalies",
                "completed",
                "检测到 1 个异常点。",
                {"anomaly_count": 1},
                10,
                {"method": "rolling_median_mad", "window": 5},
                limitations=("异常关联不代表因果。",),
            )
            store.save_analytical(artifact)
            cycle = AnalysisCycle.start("cycle-report").complete_round(
                AnalysisRound.completed(
                    RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv"}, "检查异常"),
                    (artifact.artifact_id,),
                )
            )

            report = build_html_report_from_cycle(task, cycle, store)

        self.assertIn("rolling_median_mad", report.html)
        self.assertIn("异常关联不代表因果", report.html)
        self.assertNotIn("https://", report.html)
        self.assertNotIn("src=\"http", report.html)


if __name__ == "__main__":
    unittest.main()
