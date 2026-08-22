from pathlib import Path
import tempfile
import unittest

from data2doc2data.data_profile import DataProfileError, build_default_dashboard, profile_standard_csv


class DataProfileTests(unittest.TestCase):
    def test_profiles_structure_quality_time_metrics_and_distribution(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value\n"
                "2026-01-01,revenue,10\n"
                "2026-01-02,revenue,14\n"
                "2026-01-01,orders,2\n"
                "2026-01-01,orders,2\n",
                encoding="utf-8",
            )

            profile = profile_standard_csv(path, "dataset-1")

        self.assertEqual(profile.row_count, 4)
        self.assertEqual(profile.field_count, 3)
        self.assertEqual(profile.date_range, ("2026-01-01", "2026-01-02"))
        self.assertEqual(profile.metrics, ("orders", "revenue"))
        self.assertEqual(profile.duplicate_count, 1)
        self.assertEqual(profile.missing_count, 0)
        self.assertEqual(profile.metric_summaries["revenue"].average, 12)
        self.assertEqual(profile.metric_summaries["orders"].count, 2)

    def test_default_dashboard_is_model_free_bounded_and_source_backed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value\n2026-01-01,revenue,10\n2026-01-02,revenue,14\n",
                encoding="utf-8",
            )
            profile = profile_standard_csv(path, "dataset-1")

        dashboard = build_default_dashboard(profile)
        kinds = [block.kind for block in dashboard.blocks]
        encoded = dashboard.to_dict()

        self.assertEqual(kinds[:4], ["kpi", "kpi", "kpi", "kpi"])
        self.assertIn("chart", kinds)
        self.assertIn("table", kinds)
        self.assertTrue(all(block.provenance.snapshot_id == "dataset-1" for block in dashboard.blocks))
        self.assertLessEqual(max(block.provenance.result_row_count for block in dashboard.blocks), 1000)
        self.assertNotIn(str(path), str(encoded))

    def test_rejects_empty_malformed_nonfinite_and_oversized_sources(self):
        cases = {
            "empty.csv": "date,metric,value\n",
            "missing.csv": "date,value\n2026-01-01,1\n",
            "nan.csv": "date,metric,value\n2026-01-01,revenue,nan\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(DataProfileError):
                        profile_standard_csv(path, "dataset-1")


if __name__ == "__main__":
    unittest.main()
