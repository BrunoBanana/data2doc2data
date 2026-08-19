import io
import json
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
import zipfile

from data2doc2data.ingestion import (
    IngestionError,
    IngestionPlan,
    apply_plan,
    build_proposal_prompt,
    detect_format,
    parse_plan_response,
    preview_source,
    suggest_plan,
    write_standard_csv,
)

EXCEL_EPOCH = date(1899, 12, 30)


class IngestionPlanTests(unittest.TestCase):
    def test_plan_requires_all_fields(self):
        with self.assertRaises(IngestionError):
            IngestionPlan(format="csv", date_field="日期", metric_field="指标", value_field="")

    def test_plan_rejects_unknown_format(self):
        with self.assertRaises(IngestionError):
            IngestionPlan(format="parquet", date_field="d", metric_field="m", value_field="v")

    def test_plan_round_trips_through_dict(self):
        plan = IngestionPlan(
            format="json",
            date_field="ds",
            metric_field="name",
            value_field="val",
            records_path="data.rows",
        )
        self.assertEqual(IngestionPlan.from_dict(plan.to_dict()), plan)


class FormatDetectionTests(unittest.TestCase):
    def test_detect_format_by_extension(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(detect_format(root / "a.csv"), "csv")
            self.assertEqual(detect_format(root / "b.XLSX"), "xlsx")
            self.assertEqual(detect_format(root / "c.json"), "json")

    def test_detect_format_rejects_unknown(self):
        with self.assertRaises(IngestionError):
            detect_format(Path("report.pdf"))


class CsvIngestionTests(unittest.TestCase):
    def test_preview_reports_fields_and_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "日期,指标,数值\n2026-01-05,retention_rate,0.66\n2026-01-12,retention_rate,0.65\n",
                encoding="utf-8",
            )
            preview = preview_source(path)
            self.assertEqual(preview.format, "csv")
            self.assertEqual(preview.fields, ("日期", "指标", "数值"))
            self.assertEqual(preview.row_count, 2)
            self.assertEqual(preview.sample_rows[0]["指标"], "retention_rate")

    def test_suggest_plan_matches_chinese_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text("日期,指标,数值\n2026-01-05,retention_rate,0.66\n", encoding="utf-8")
            preview = preview_source(path)
            plan = suggest_plan(preview)
            self.assertIsNotNone(plan)
            self.assertEqual(plan.date_field, "日期")
            self.assertEqual(plan.metric_field, "指标")
            self.assertEqual(plan.value_field, "数值")

    def test_suggest_plan_returns_none_without_clear_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
            self.assertIsNone(suggest_plan(preview_source(path)))

    def test_apply_plan_converts_rows_with_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value\n2026-01-05,retention_rate,0.66\n2026-01-12,retention_rate,0.65\n",
                encoding="utf-8",
            )
            plan = IngestionPlan(format="csv", date_field="date", metric_field="metric", value_field="value")
            result = apply_plan(path, plan)
            self.assertEqual(len(result.rows), 2)
            self.assertEqual(result.rows[0].source_row, 2)
            self.assertEqual(result.rows[0].value, 0.66)
            self.assertEqual(result.skipped, 0)

    def test_apply_plan_skips_unparseable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text(
                "date,metric,value\n2026-01-05,retention_rate,0.66\nbad-date,retention_rate,0.65\n2026-01-12,,0.64\n",
                encoding="utf-8",
            )
            plan = IngestionPlan(format="csv", date_field="date", metric_field="metric", value_field="value")
            result = apply_plan(path, plan)
            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.skipped, 2)
            self.assertTrue(any("第 3 行" in warning for warning in result.warnings))

    def test_apply_plan_fails_when_nothing_convertible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.csv"
            path.write_text("date,metric,value\nbad,also-bad,worse\n", encoding="utf-8")
            plan = IngestionPlan(format="csv", date_field="date", metric_field="metric", value_field="value")
            with self.assertRaises(IngestionError):
                apply_plan(path, plan)


class JsonIngestionTests(unittest.TestCase):
    def test_preview_top_level_array(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            path.write_text(
                json.dumps(
                    [
                        {"ds": "2026-01-05", "name": "retention_rate", "val": 0.66},
                        {"ds": "2026-01-12", "name": "retention_rate", "val": 0.65},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            preview = preview_source(path)
            self.assertEqual(preview.format, "json")
            self.assertEqual(preview.fields, ("ds", "name", "val"))
            self.assertEqual(preview.row_count, 2)

    def test_preview_nested_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            path.write_text(
                json.dumps({"data": [{"日期": "2026-01-05", "指标": "留存", "数值": 1}]}),
                encoding="utf-8",
            )
            preview = preview_source(path)
            self.assertEqual(preview.fields, ("日期", "指标", "数值"))
            plan = suggest_plan(preview)
            self.assertIsNotNone(plan)
            self.assertEqual(plan.records_path, "data")

    def test_apply_plan_nested_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            path.write_text(
                json.dumps({"data": [{"ds": "2026-01-05", "name": "retention", "val": 0.5}]}),
                encoding="utf-8",
            )
            plan = IngestionPlan(
                format="json",
                date_field="ds",
                metric_field="name",
                value_field="val",
                records_path="data",
            )
            result = apply_plan(path, plan)
            self.assertEqual(len(result.rows), 1)
            self.assertEqual(result.rows[0].value, 0.5)

    def test_apply_plan_with_missing_records_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            path.write_text(json.dumps({"rows": []}), encoding="utf-8")
            plan = IngestionPlan(
                format="json",
                date_field="ds",
                metric_field="name",
                value_field="val",
                records_path="data",
            )
            with self.assertRaises(IngestionError):
                apply_plan(path, plan)


class XlsxIngestionTests(unittest.TestCase):
    def test_preview_and_apply_xlsx_inline_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.xlsx"
            path.write_bytes(
                _build_xlsx(
                    [
                        [("s", "日期"), ("s", "指标"), ("s", "数值")],
                        [("s", "2026-01-05"), ("s", "retention_rate"), ("s", "0.66")],
                        [("s", "2026-01-12"), ("s", "retention_rate"), ("s", "0.65")],
                    ]
                )
            )
            preview = preview_source(path)
            self.assertEqual(preview.format, "xlsx")
            self.assertEqual(preview.fields, ("A", "B", "C"))
            self.assertEqual(preview.header_values, ("日期", "指标", "数值"))
            self.assertEqual(preview.row_count, 2)
            plan = IngestionPlan(format="xlsx", date_field="A", metric_field="B", value_field="C")
            result = apply_plan(path, plan)
            self.assertEqual(len(result.rows), 2)
            self.assertEqual(result.rows[0].metric, "retention_rate")

    def test_apply_plan_xlsx_excel_serial_date(self):
        serial = 45292
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.xlsx"
            path.write_bytes(
                _build_xlsx(
                    [
                        [("s", "日期"), ("s", "指标"), ("s", "数值")],
                        [("n", str(serial)), ("s", "retention_rate"), ("n", "0.66")],
                    ]
                )
            )
            plan = IngestionPlan(format="xlsx", date_field="A", metric_field="B", value_field="C")
            result = apply_plan(path, plan)
            self.assertEqual(result.rows[0].date, EXCEL_EPOCH + timedelta(days=serial))

    def test_read_xlsx_missing_sheet(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.xlsx"
            path.write_bytes(_build_xlsx([[("s", "日期")]]))
            plan = IngestionPlan(
                format="xlsx",
                date_field="A",
                metric_field="A",
                value_field="A",
                sheet="不存在",
            )
            with self.assertRaises(IngestionError):
                apply_plan(path, plan)


class StandardCsvTests(unittest.TestCase):
    def test_write_standard_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(
                json.dumps({"data": [{"ds": "2026-01-05", "name": "retention", "val": 0.66}]}),
                encoding="utf-8",
            )
            plan = IngestionPlan(
                format="json",
                date_field="ds",
                metric_field="name",
                value_field="val",
                records_path="data",
            )
            result = apply_plan(source, plan)
            target = root / "standard.csv"
            write_standard_csv(result.rows, target)
            preview = preview_source(target)
            self.assertEqual(preview.fields, ("date", "metric", "value"))
            self.assertEqual(preview.row_count, 1)


class AgentProposalTests(unittest.TestCase):
    def test_parse_plan_response_fenced_json(self):
        text = '分析完成，方案如下：\n```json\n{"format": "json", "date_field": "ds", "metric_field": "name", "value_field": "val", "records_path": "data"}\n```'
        plan = parse_plan_response(text)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.date_field, "ds")
        self.assertEqual(plan.records_path, "data")

    def test_parse_plan_response_bare_json(self):
        text = '{"format": "csv", "date_field": "日期", "metric_field": "指标", "value_field": "数值"}'
        plan = parse_plan_response(text)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.date_field, "日期")

    def test_parse_plan_response_error_object(self):
        self.assertIsNone(parse_plan_response('{"error": "文件没有数值列"}'))

    def test_parse_plan_response_without_json(self):
        self.assertIsNone(parse_plan_response("这个文件看起来没有指标数据。"))

    def test_build_proposal_prompt_mentions_fields_and_output_schema(self):
        prompt = build_proposal_prompt(_csv_preview(), "/tmp/metrics.csv")
        self.assertIn("/tmp/metrics.csv", prompt)
        self.assertIn("date_field", prompt)
        self.assertIn("date,metric,value", prompt)


class ApiSnapshotGuardTests(unittest.TestCase):
    def test_fetch_rejects_non_https(self):
        from data2doc2data.ingestion import fetch_api_snapshot

        with self.assertRaises(IngestionError):
            fetch_api_snapshot("http://api.example.com/metrics", target_dir=Path("/tmp/d2d2d"))


def _csv_preview():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "metrics.csv"
        path.write_text("date,metric,value\n2026-01-05,retention_rate,0.66\n", encoding="utf-8")
        return preview_source(path)


def _build_xlsx(rows: list[list[tuple[str, str]]]) -> bytes:
    """Build a minimal valid xlsx with inline strings and numbers."""
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, (kind, value) in enumerate(row):
            reference = f"{_column_letter(column_index)}{row_index}"
            if kind == "s":
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{_escape(value)}</t></is></c>')
            else:
                cells.append(f'<c r="{reference}"><v>{_escape(value)}</v></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" r:id="rId1"/></sheets></workbook>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return buffer.getvalue()


def _column_letter(index: int) -> str:
    name = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


if __name__ == "__main__":
    unittest.main()
