from pathlib import Path
import tempfile
import unittest

from data2doc2data.analytical_table import AnalyticalTableError, load_analytical_table


class AnalyticalTableTests(unittest.TestCase):
    def test_loads_required_long_form_without_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text("date,metric,value\n2026-01-01,gmv,10\n", encoding="utf-8")

            table = load_analytical_table(path, "snapshot-1")

        self.assertEqual(table.dimensions, ())
        self.assertEqual(dict(table.rows[0].dimensions), {})
        self.assertEqual(table.rows[0].metric, "gmv")
        self.assertEqual(table.source_row_count, 1)

    def test_preserves_optional_dimensions_in_header_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value,region,channel\n"
                "2026-01-01,GMV,10,华东,直播\n",
                encoding="utf-8",
            )

            table = load_analytical_table(path, "snapshot-1")

        self.assertEqual(table.dimensions, ("region", "channel"))
        self.assertEqual(dict(table.rows[0].dimensions), {"region": "华东", "channel": "直播"})
        self.assertEqual(table.rows[0].metric, "gmv")

    def test_counts_incomplete_required_cells_but_keeps_valid_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value,region\n"
                "2026-01-01,gmv,10,华东\n"
                "2026-01-02,,12,华南\n",
                encoding="utf-8",
            )

            table = load_analytical_table(path, "snapshot-1")

        self.assertEqual(table.source_row_count, 2)
        self.assertEqual(table.missing_required_count, 1)
        self.assertEqual(len(table.rows), 1)

    def test_rejects_missing_fields_duplicate_headers_and_invalid_dimensions(self):
        cases = {
            "missing.csv": "date,value\n2026-01-01,10\n",
            "duplicate.csv": "date,metric,value,region,region\n2026-01-01,gmv,10,a,b\n",
            "invalid.csv": "date,metric,value,bad field\n2026-01-01,gmv,10,a\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in cases.items():
                with self.subTest(name=name):
                    path = root / name
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(AnalyticalTableError):
                        load_analytical_table(path, "snapshot-1")


if __name__ == "__main__":
    unittest.main()
