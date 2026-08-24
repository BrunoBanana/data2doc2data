import tempfile
from pathlib import Path
import unittest

from data2doc2data.source_resolver import SourceResolver, SourceResolverError


class SourceResolverTests(unittest.TestCase):
    def test_markdown_report_yields_text_and_embedded_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "review.md"
            source.write_text(
                "# 复盘\n转化率下降。\n\n"
                "| date | metric | value |\n"
                "| --- | --- | ---: |\n"
                "| 2026-01-01 | conversion | 0.20 |\n",
                encoding="utf-8",
            )

            resolved = SourceResolver().resolve((source,))

        self.assertEqual(resolved.modalities, ("data", "text"))
        self.assertEqual(resolved.datasets[0].row_count, 1)
        self.assertEqual(resolved.datasets[0].fields, ("date", "metric", "value"))
        self.assertTrue(resolved.documents[0].sections)
        self.assertEqual(resolved.diagnostics, ())

    def test_csv_and_document_pair_resolve_without_merging_raw_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            csv_path.write_text("date,metric,value\n2026-01-01,revenue,12\n", encoding="utf-8")
            document_path = root / "notes.txt"
            document_path.write_text("Revenue increased after launch.", encoding="utf-8")

            resolved = SourceResolver((root,)).resolve((csv_path, document_path))

        self.assertEqual(resolved.modalities, ("data", "text"))
        self.assertEqual(resolved.datasets[0].row_count, 1)
        self.assertEqual(len(resolved.documents), 1)

    def test_partial_failures_are_bounded_and_outside_roots_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory)
            valid = root / "valid.md"
            valid.write_text("# Valid\nEvidence.", encoding="utf-8")
            unsupported = root / "image.bin"
            unsupported.write_bytes(b"not a supported document")

            resolved = SourceResolver((root,)).resolve((valid, unsupported))
            self.assertEqual(len(resolved.documents), 1)
            self.assertEqual(len(resolved.diagnostics), 1)
            self.assertIn("unsupported", resolved.diagnostics[0].message)

            escaped = Path(outside) / "outside.md"
            escaped.write_text("outside", encoding="utf-8")
            with self.assertRaisesRegex(SourceResolverError, "approved roots"):
                SourceResolver((root,)).resolve((escaped,))


if __name__ == "__main__":
    unittest.main()
