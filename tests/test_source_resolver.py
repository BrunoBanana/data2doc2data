import tempfile
from pathlib import Path
import unittest
import zipfile

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

    def test_directory_discovers_supported_sources_without_treating_rules_as_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metrics.csv").write_text("date,metric,value\n2026-01-01,revenue,12\n", encoding="utf-8")
            documents = root / "documents"
            documents.mkdir()
            (documents / "review.md").write_text("# Review\nRevenue increased.", encoding="utf-8")
            (root / "rules.json").write_text('{"version": 1}', encoding="utf-8")

            resolved = SourceResolver((root,)).resolve((root,))

        self.assertEqual(resolved.modalities, ("data", "text"))
        self.assertEqual(len(resolved.datasets), 1)
        self.assertEqual(len(resolved.documents), 1)
        self.assertEqual(resolved.diagnostics, ())

    def test_html_report_yields_narrative_chart_context_and_embedded_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "review.html"
            source.write_text(
                "<html><body><h1>业务复盘</h1><p>毛利率下降。</p>"
                '<img alt="毛利率趋势图">'
                "<table><tr><th>date</th><th>metric</th><th>value</th></tr>"
                "<tr><td>2026-01-01</td><td>gross_margin_rate</td><td>0.36</td></tr>"
                "<tr><td>2026-01-08</td><td>gross_margin_rate</td><td>0.31</td></tr>"
                "</table></body></html>",
                encoding="utf-8",
            )

            resolved = SourceResolver().resolve((source,))

        self.assertEqual(resolved.modalities, ("data", "text"))
        self.assertEqual(resolved.datasets[0].row_count, 2)
        self.assertIn("毛利率趋势图", resolved.documents[0].sections[0].text)

    def test_word_review_yields_narrative_accessible_chart_context_and_embedded_table(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "review.docx"
            document = (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                "<w:body><w:p><w:r><w:t>毛利率下降需要复核促销。</w:t></w:r></w:p>"
                '<wp:docPr id="1" name="chart" descr="毛利率趋势图"/>'
                "<w:tbl>"
                "<w:tr><w:tc><w:p><w:r><w:t>date</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>metric</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>value</w:t></w:r></w:p></w:tc></w:tr>"
                "<w:tr><w:tc><w:p><w:r><w:t>2026-01-01</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>gross_margin_rate</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>0.36</w:t></w:r></w:p></w:tc></w:tr>"
                "<w:tr><w:tc><w:p><w:r><w:t>2026-01-08</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>gross_margin_rate</w:t></w:r></w:p></w:tc>"
                "<w:tc><w:p><w:r><w:t>0.31</w:t></w:r></w:p></w:tc></w:tr>"
                "</w:tbl></w:body></w:document>"
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", document)

            resolved = SourceResolver().resolve((source,))

        self.assertEqual(resolved.modalities, ("data", "text"))
        self.assertEqual(resolved.datasets[0].row_count, 2)
        self.assertIn("毛利率趋势图", resolved.documents[0].sections[0].text)

    def test_excel_workbook_yields_local_dataset_without_optional_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "metrics.xlsx"
            sheet = (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                '<row r="1"><c r="A1" t="inlineStr"><is><t>date</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>metric</t></is></c>'
                '<c r="C1" t="inlineStr"><is><t>value</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>2026-01-01</t></is></c>'
                '<c r="B2" t="inlineStr"><is><t>revenue</t></is></c><c r="C2"><v>120</v></c></row>'
                '<row r="3"><c r="A3" t="inlineStr"><is><t>2026-01-08</t></is></c>'
                '<c r="B3" t="inlineStr"><is><t>revenue</t></is></c><c r="C3"><v>160</v></c></row>'
                "</sheetData></worksheet>"
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", sheet)

            resolved = SourceResolver().resolve((source,))

        self.assertEqual(resolved.modalities, ("data",))
        self.assertEqual(resolved.datasets[0].row_count, 2)
        self.assertEqual(resolved.datasets[0].rows[1]["value"], "160")

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
