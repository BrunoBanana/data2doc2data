from datetime import date, timedelta
import math
from pathlib import Path
import tempfile
import unittest

from data2doc2data.analytical_table import load_analytical_table
from data2doc2data.diagnostics import (
    SeriesPoint,
    compare_periods,
    decompose_change,
    detect_anomalies,
    detect_change_points,
    segment_rank,
)


def series(values: list[float]) -> tuple[SeriesPoint, ...]:
    start = date(2026, 1, 1)
    return tuple(SeriesPoint(start + timedelta(days=index), value) for index, value in enumerate(values))


class DiagnosticTests(unittest.TestCase):
    def test_compare_periods_reports_auditable_change(self):
        artifact = compare_periods(series([10, 10, 12, 14]), split=2)

        self.assertEqual(artifact.status, "completed")
        self.assertEqual(artifact.observations["baseline"], 10)
        self.assertEqual(artifact.observations["current"], 13)
        self.assertEqual(artifact.observations["absolute_change"], 3)
        self.assertEqual(artifact.observations["change_percent"], 30)
        self.assertEqual(artifact.sample_size, 4)

    def test_compare_periods_handles_zero_baseline_without_fabricating_percent(self):
        artifact = compare_periods(series([0, 0, 1, 2]), split=2)

        self.assertIsNone(artifact.observations["change_percent"])
        self.assertIn("zero", artifact.diagnostics[0]["code"])

    def test_detect_anomalies_finds_robust_spike_without_calling_neighbors_anomalies(self):
        artifact = detect_anomalies(series([10, 10, 11, 10, 10, 50, 11, 10]), window=5)

        self.assertEqual(
            [item["index"] for item in artifact.observations["anomalies"]],
            [5],
        )
        self.assertEqual(artifact.parameters["method"], "rolling_median_mad")

    def test_detect_change_point_finds_sustained_level_shift(self):
        artifact = detect_change_points(series([10] * 8 + [20] * 8), minimum_window=4)

        self.assertEqual(artifact.status, "completed")
        self.assertEqual(artifact.observations["change_index"], 8)
        self.assertGreater(artifact.observations["effect_size"], 1)
        self.assertEqual(artifact.observations["before_mean"], 10)
        self.assertEqual(artifact.observations["after_mean"], 20)

    def test_diagnostics_return_unavailable_for_insufficient_or_degenerate_series(self):
        anomaly = detect_anomalies(series([1, 2, 3]), window=5)
        change = detect_change_points(series([4] * 10), minimum_window=3)

        self.assertEqual(anomaly.status, "unavailable")
        self.assertEqual(change.status, "unavailable")
        self.assertTrue(change.limitations)

    def test_series_rejects_nonfinite_values(self):
        with self.assertRaises(ValueError):
            SeriesPoint(date(2026, 1, 1), math.nan)

    def test_decomposes_additive_change_by_channel(self):
        table = dimension_table(
            "gmv",
            [
                ("2026-01-01", 10, "直播"),
                ("2026-01-02", 10, "直播"),
                ("2026-01-03", 40, "直播"),
                ("2026-01-04", 40, "直播"),
                ("2026-01-01", 20, "搜索"),
                ("2026-01-02", 20, "搜索"),
                ("2026-01-03", 25, "搜索"),
                ("2026-01-04", 25, "搜索"),
            ],
        )

        artifact = decompose_change(table, metric="gmv", dimension="channel")

        self.assertEqual(artifact.status, "completed")
        contributors = artifact.observations["contributors"]
        self.assertEqual(contributors[0]["member"], "直播")
        self.assertEqual(contributors[0]["delta"], 60)
        self.assertEqual(
            sum(item["delta"] for item in contributors),
            artifact.observations["total_delta"],
        )

    def test_ranks_segments_by_current_value_and_change(self):
        table = dimension_table(
            "orders",
            [
                ("2026-01-01", 5, "A"),
                ("2026-01-02", 10, "A"),
                ("2026-01-01", 20, "B"),
                ("2026-01-02", 21, "B"),
            ],
        )

        artifact = segment_rank(table, metric="orders", dimension="channel", split_date=date(2026, 1, 2))

        self.assertEqual(artifact.observations["by_current"][0]["member"], "B")
        self.assertEqual(artifact.observations["by_change"][0]["member"], "A")

    def test_refuses_rate_decomposition_without_numerator_and_denominator(self):
        table = dimension_table(
            "refund_rate",
            [
                ("2026-01-01", 0.1, "直播"),
                ("2026-01-02", 0.2, "直播"),
            ],
        )

        artifact = decompose_change(table, metric="refund_rate", dimension="channel")

        self.assertEqual(artifact.status, "unavailable")
        self.assertTrue(any("分子" in item and "分母" in item for item in artifact.limitations))

    def test_dimension_tools_report_unavailable_when_dimension_is_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value\n2026-01-01,gmv,10\n2026-01-02,gmv,20\n",
                encoding="utf-8",
            )
            table = load_analytical_table(path, "snapshot-1")

        artifact = segment_rank(table, metric="gmv", dimension="channel")

        self.assertEqual(artifact.status, "unavailable")
        self.assertIn("channel", artifact.limitations[0])


def dimension_table(metric: str, values: list[tuple[str, float, str]]):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "metrics.csv"
        rows = "".join(f"{item_date},{metric},{value},{channel}\n" for item_date, value, channel in values)
        path.write_text(f"date,metric,value,channel\n{rows}", encoding="utf-8")
        return load_analytical_table(path, "snapshot-1")


if __name__ == "__main__":
    unittest.main()
