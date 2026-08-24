from datetime import date, timedelta
import math
import unittest

from data2doc2data.diagnostics import (
    SeriesPoint,
    compare_periods,
    detect_anomalies,
    detect_change_points,
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


if __name__ == "__main__":
    unittest.main()
