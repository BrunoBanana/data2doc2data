from html.parser import HTMLParser
import unittest

from data2doc2data.reporting import build_html_report
from data2doc2data.workspace import AnalysisTask, SnapshotRef


class _Parser(HTMLParser):
    def error(self, message):  # pragma: no cover - compatibility hook
        raise AssertionError(message)


class ReportingTests(unittest.TestCase):
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
        graph = {"contract_version": 1, "graph_id": "graph-1", "nodes": [{"node_id": "hypothesis-1", "kind": "hypothesis", "label": "价格影响收入", "status": "insufficient", "artifact_ref": None}], "edges": []}

        artifact = build_html_report(task, dashboard, text, graph, run_count=1)

        self.assertTrue(artifact.filename.endswith(".html"))
        self.assertIn("<h2>Executive Summary</h2>", artifact.html)
        self.assertLess(artifact.html.index("Executive Summary"), artifact.html.index("关键发现"))
        self.assertIn("<svg", artifact.html)
        self.assertIn("推荐下一步", artifact.html)
        self.assertIn("仍需回答的问题", artifact.html)
        self.assertIn("局限与假设", artifact.html)
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


if __name__ == "__main__":
    unittest.main()
