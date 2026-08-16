from datetime import date
import math
import unittest

from data2doc2data.metrics import (
    InputValidationError,
    MetricRow,
    MetricSpec,
    SignalEngine,
)


class MetricTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            MetricRow(date(2026, 1, 1), "retention_rate", 0.66),
            MetricRow(date(2026, 1, 8), "retention_rate", 0.64),
            MetricRow(date(2026, 1, 15), "retention_rate", 0.58),
            MetricRow(date(2026, 1, 22), "retention_rate", 0.56),
        ]

    def test_previous_period_mean_records_ranges_and_counts(self):
        spec = MetricSpec(name="retention_rate", aggregation="mean", comparison="previous_period")

        signal = SignalEngine().build(spec, self.rows)

        self.assertEqual(signal.baseline_count, 2)
        self.assertEqual(signal.current_count, 2)
        self.assertEqual(signal.baseline_range.start.isoformat(), "2026-01-01")
        self.assertEqual(signal.baseline_range.end.isoformat(), "2026-01-08")
        self.assertEqual(signal.current_range.start.isoformat(), "2026-01-15")
        self.assertAlmostEqual(signal.absolute_change, -0.08)
        self.assertEqual(signal.spec, spec)

    def test_previous_period_uses_equal_recent_windows_when_history_is_odd(self):
        rows = [MetricRow(date(2025, 12, 25), "retention_rate", 0.90), *self.rows]

        signal = SignalEngine().build(
            MetricSpec(name="retention_rate", comparison="previous_period"),
            rows,
        )

        self.assertAlmostEqual(signal.baseline, 0.65)
        self.assertAlmostEqual(signal.current, 0.57)
        self.assertEqual(signal.baseline_range.start, date(2026, 1, 1))

    def test_duplicate_dates_are_rejected_by_default(self):
        duplicate_rows = self.rows + [MetricRow(date(2026, 1, 1), "retention_rate", 0.60)]

        with self.assertRaisesRegex(InputValidationError, "duplicate"):
            SignalEngine().build(MetricSpec(name="retention_rate"), duplicate_rows)

    def test_duplicate_dates_can_be_averaged_explicitly(self):
        duplicate_rows = [
            MetricRow(date(2026, 1, 1), "revenue", 10.0),
            MetricRow(date(2026, 1, 1), "revenue", 14.0),
            MetricRow(date(2026, 1, 2), "revenue", 18.0),
        ]

        signal = SignalEngine().build(
            MetricSpec(name="revenue", duplicate_policy="mean"),
            duplicate_rows,
        )

        self.assertEqual(signal.baseline, 12.0)
        self.assertEqual(signal.current, 18.0)

    def test_supported_aggregations_are_applied_to_each_window(self):
        expectations = {
            "mean": (0.65, 0.57),
            "sum": (1.30, 1.14),
            "latest": (0.64, 0.56),
            "min": (0.64, 0.56),
            "max": (0.66, 0.58),
        }
        for aggregation, expected in expectations.items():
            with self.subTest(aggregation=aggregation):
                signal = SignalEngine().build(
                    MetricSpec(name="retention_rate", aggregation=aggregation),
                    self.rows,
                )
                self.assertAlmostEqual(signal.baseline, expected[0])
                self.assertAlmostEqual(signal.current, expected[1])

    def test_engine_rejects_non_finite_values_from_direct_callers(self):
        rows = [
            MetricRow(date(2026, 1, 1), "revenue", 1.0),
            MetricRow(date(2026, 1, 2), "revenue", math.nan),
        ]

        with self.assertRaisesRegex(InputValidationError, "finite"):
            SignalEngine().build(MetricSpec(name="revenue"), rows)

    def test_metric_spec_rejects_invalid_configuration(self):
        with self.assertRaisesRegex(InputValidationError, "aggregation"):
            MetricSpec(name="revenue", aggregation="median")
        with self.assertRaisesRegex(InputValidationError, "threshold"):
            MetricSpec(name="revenue", threshold=-1)
        with self.assertRaisesRegex(InputValidationError, "minimum"):
            MetricSpec(name="revenue", minimum_observations=1)


if __name__ == "__main__":
    unittest.main()
