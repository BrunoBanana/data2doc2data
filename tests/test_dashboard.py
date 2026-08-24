from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
from data2doc2data.artifacts import ArtifactStore
from data2doc2data.dashboard import (
    DashboardBlock,
    DashboardContractError,
    DashboardSpec,
    FlintChartSpec,
    QueryProvenance,
    build_artifact_dashboard,
)
from data2doc2data.diagnostics import AnalyticalArtifact


class DashboardContractTests(unittest.TestCase):
    def test_versioned_dashboard_round_trip_keeps_query_provenance(self):
        provenance = QueryProvenance(
            snapshot_id="dataset-1",
            sha256="a" * 64,
            expression="group metric by date and average value",
            fields=("date", "metric", "value"),
            result_row_count=12,
        )
        chart = FlintChartSpec(
            mark="line",
            encoding={
                "x": {"field": "date", "type": "temporal"},
                "y": {"field": "value", "type": "quantitative"},
                "color": {"field": "metric", "type": "nominal"},
            },
        )
        dashboard = DashboardSpec(
            dashboard_id="dashboard-1",
            title="数据概览",
            blocks=(DashboardBlock("trend", "chart", "指标趋势", provenance, chart=chart),),
        )

        self.assertEqual(DashboardSpec.from_dict(dashboard.to_dict()), dashboard)
        self.assertEqual(dashboard.contract_version, 1)

    def test_chart_rejects_unsupported_marks_transforms_and_fields(self):
        with self.assertRaisesRegex(DashboardContractError, "mark"):
            FlintChartSpec(mark="javascript", encoding={})
        with self.assertRaisesRegex(DashboardContractError, "transform"):
            FlintChartSpec(mark="bar", encoding={}, transforms=({"type": "eval", "code": "alert(1)"},))
        with self.assertRaisesRegex(DashboardContractError, "transform"):
            FlintChartSpec(
                mark="bar",
                encoding={"x": {"field": "metric", "type": "nominal"}},
                transforms=({"type": "aggregate", "op": "mean", "field": "value", "code": "alert(1)"},),
            )
        with self.assertRaisesRegex(DashboardContractError, "field"):
            FlintChartSpec(mark="bar", encoding={"x": {"field": "__proto__", "type": "nominal"}})

    def test_provenance_rejects_executable_or_unbounded_results(self):
        for expression in ("SELECT * FROM data", "import os", "<script>alert(1)</script>"):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(DashboardContractError, "expression"):
                    QueryProvenance("dataset-1", "a" * 64, expression, ("value",), 1)
        with self.assertRaisesRegex(DashboardContractError, "row"):
            QueryProvenance("dataset-1", "a" * 64, "average value", ("value",), 1001)

    def test_block_requires_matching_payload_and_safe_stable_ids(self):
        provenance = QueryProvenance("dataset-1", "a" * 64, "count rows", ("value",), 1)
        with self.assertRaisesRegex(DashboardContractError, "chart"):
            DashboardBlock("block-1", "chart", "Trend", provenance)
        with self.assertRaisesRegex(DashboardContractError, "block_id"):
            DashboardBlock("bad/id", "kpi", "Rows", provenance, value=12)

    def test_cycle_artifact_becomes_a_provenance_backed_diagnostic_block(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            artifact = AnalyticalArtifact(
                "artifact-anomaly",
                "detect_anomalies",
                "completed",
                "检测到 1 个异常点。",
                {"anomalies": [{"date": "2026-01-05", "value": 50}], "anomaly_count": 1},
                10,
                {"method": "rolling_median_mad", "window": 5},
                limitations=("异常不代表因果。",),
                source_refs=("dataset-1",),
            )
            store.save_analytical(artifact)
            decision = RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv"}, "检查异常")
            cycle = AnalysisCycle.start("cycle-dashboard").complete_round(
                AnalysisRound.completed(decision, (artifact.artifact_id,))
            )

            dashboard = build_artifact_dashboard(cycle, store)

        block = dashboard.blocks[0]
        self.assertEqual(block.kind, "anomalies")
        self.assertEqual(block.provenance.artifact_ref, artifact.artifact_id)
        self.assertEqual(block.provenance.method, "detect_anomalies")
        self.assertIn("异常不代表因果。", block.provenance.limitations)


if __name__ == "__main__":
    unittest.main()
