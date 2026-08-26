from datetime import date
from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis import (
    MAX_CSV_BYTES,
    MAX_DOCUMENT_BYTES,
    DocumentContext,
    InputValidationError,
    MetricRow,
    Signal,
    _build_signal,
    _validate,
    _verify_document_condition,
    analyze,
)
from data2doc2data.config import Profile
from data2doc2data.demo_scenarios import DemoScenarioCatalog
from data2doc2data.rules import default_ruleset


class AnalysisTests(unittest.TestCase):
    def test_demo_scenarios_match_golden_validation_and_provenance(self):
        catalog = DemoScenarioCatalog.load()
        expected = {
            "growth-quality-alert": {
                "verification": "confirmed",
                "rows": tuple(range(2, 14)),
                "lines": (7, 7),
                "csv_sha256": "4a1c362ea2aeac65947c37647b396fa2439e4f7f8672a9443b0b58e9d0153f91",
                "document_sha256": "ad1b88cb0698bdbe221c10b1fc87fee414253e84db2b6da909f83593d4d3b18c",
            },
            "strategy-data-conflict": {
                "verification": "not_confirmed",
                "rows": tuple(range(2, 14)),
                "lines": (5, 6),
                "csv_sha256": "ca32924c575267a45adc7adb3f5e129ba92d69b9758b700710e750d561af10bc",
                "document_sha256": "90c7513c20a071e5f0ec3f5eec4618780d4f6607d62a5e82c439202d7c7bcf09",
            },
            "insufficient-evidence": {
                "verification": "unavailable",
                "rows": tuple(range(2, 8)),
                "lines": (7, 7),
                "csv_sha256": "804dcd9390e16b201320fb17be47636b6e9234ad76b58f0eddf93c4b18a84766",
                "document_sha256": "45016d683f3d070fcf9922ee15cd51e381ee664934cddb826bc0c41519bdf63d",
            },
        }

        for scenario in catalog.list():
            with self.subTest(scenario=scenario.id):
                metrics_path, document_path = catalog.sources(scenario.id)
                profile = Profile("local", str(metrics_path), str(document_path.parent))
                result = analyze(scenario.suggested_question, profile)
                csv_source, document_source = result.provenance.sources
                golden = expected[scenario.id]

                self.assertEqual(result.validation.status, scenario.expected_validation)
                self.assertEqual(result.verification.status, golden["verification"])
                self.assertEqual(csv_source.path, str(metrics_path.resolve()))
                self.assertEqual(document_source.path, str(document_path.resolve()))
                self.assertEqual(csv_source.sha256, golden["csv_sha256"])
                self.assertEqual(document_source.sha256, golden["document_sha256"])
                self.assertEqual(csv_source.rows, golden["rows"])
                self.assertEqual(
                    (document_source.start_line, document_source.end_line),
                    golden["lines"],
                )

    def test_demo_profile_uses_the_catalog_default_sources(self):
        metrics_path, document_path = DemoScenarioCatalog.load().sources("growth-quality-alert")

        result = analyze("留存为什么下降？", Profile.demo())
        csv_source, document_source = result.provenance.sources

        self.assertEqual(csv_source.path, str(metrics_path.resolve()))
        self.assertEqual(document_source.path, str(document_path.resolve()))

    def test_analysis_returns_signal_context_and_evidence_for_demo(self):
        result = analyze("Why did retention fall?", Profile.demo())

        self.assertEqual(result.signal.metric, "retention_rate")
        self.assertTrue(result.context.source.endswith("strategy.md"))
        self.assertIn(result.validation.status, {"supported", "mixed", "insufficient"})
        self.assertGreaterEqual(len(result.evidence), 2)

    def test_demo_document_condition_is_supported_after_second_data_test(self):
        result = analyze("Why did retention fall?", Profile.demo())

        self.assertEqual(result.validation.status, "supported")
        self.assertEqual(result.verification.status, "confirmed")
        self.assertEqual(result.verification.metric, "activation_rate")

    def test_demo_analysis_uses_chinese_generated_copy(self):
        result = analyze("留存为什么下降？", Profile.demo())

        self.assertIn("留存率", result.signal.summary)
        self.assertIn("获得数据支持", result.validation.summary)
        self.assertTrue(result.evidence[0].startswith("指标来源："))
        self.assertIn("本地分析", result.limitation)

    def test_analysis_result_serializes_metric_ranges_as_iso_dates(self):
        payload = analyze("retention", Profile.demo()).to_dict()

        self.assertEqual(payload["signal"]["baseline_range"]["start"], "2026-01-05")
        self.assertEqual(payload["signal"]["current_range"]["end"], "2026-02-09")

    def test_analysis_records_exact_rows_lines_hashes_and_engine_version(self):
        result = analyze("retention", Profile.demo())

        csv_source, document_source = result.provenance.sources
        self.assertEqual(csv_source.rows, tuple(range(2, 14)))
        self.assertRegex(csv_source.sha256, r"^[0-9a-f]{64}$")
        self.assertGreaterEqual(document_source.start_line, 1)
        self.assertGreaterEqual(document_source.end_line, document_source.start_line)
        self.assertEqual(document_source.sha256, result.context.sha256)
        self.assertTrue(result.provenance.engine_version)
        self.assertEqual(
            result.provenance.analysis_id,
            analyze("retention", Profile.demo()).provenance.analysis_id,
        )

    def test_local_analysis_rejects_a_csv_missing_required_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text("day,amount\n2026-01-05,12\n", encoding="utf-8")
            (notes / "decision.md").write_text("Review retention weekly.", encoding="utf-8")

            with self.assertRaisesRegex(InputValidationError, "date, metric, value"):
                analyze("Why did retention fall?", Profile("local", str(csv_path), str(notes)))

    def test_local_analysis_rejects_missing_document_directory(self):
        profile = Profile("local", "/missing/metrics.csv", "/missing/notes")

        with self.assertRaisesRegex(InputValidationError, "CSV file"):
            analyze("What changed?", profile)

    def test_chinese_retention_question_resolves_to_retention_rate(self):
        result = analyze("留存为什么下降？", Profile.demo())

        self.assertEqual(result.signal.metric, "retention_rate")
        self.assertGreater(result.context.relevance, 0)

    def test_zero_relevance_context_cannot_be_mixed(self):
        signal = Signal("retention_rate", 0.66, 0.56, -15.0, "down", "Retention fell.")
        context = DocumentContext("decision.md", "Retention safeguard", 0)

        validation = _validate(signal, context)

        self.assertEqual(validation.status, "insufficient")

    def test_analysis_limitation_has_no_release_label(self):
        limitation = analyze("retention", Profile.demo()).limitation

        self.assertNotIn("v0.1", limitation)
        self.assertNotIn("v1.1", limitation)

    def test_unresolved_metric_requires_an_override(self):
        with self.assertRaisesRegex(InputValidationError, "Specify --metric"):
            analyze("What changed?", Profile.demo())

    def test_metric_override_selects_an_available_metric(self):
        result = analyze("What changed?", Profile.demo(), metric_override="retention_rate")

        self.assertEqual(result.signal.metric, "retention_rate")

    def test_unknown_metric_override_is_rejected(self):
        with self.assertRaisesRegex(InputValidationError, "is not available"):
            analyze("What changed?", Profile.demo(), metric_override="conversion_rate")

    def test_one_observation_cannot_produce_a_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text(
                "date,metric,value\n2026-01-05,retention_rate,0.66\n",
                encoding="utf-8",
            )
            (notes / "decision.md").write_text("Retention needs review.", encoding="utf-8")

            with self.assertRaisesRegex(InputValidationError, "at least two"):
                analyze("retention", Profile("local", str(csv_path), str(notes)))

    def test_too_many_local_documents_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text(
                "date,metric,value\n2026-01-05,retention_rate,0.66\n2026-01-06,retention_rate,0.55\n",
                encoding="utf-8",
            )
            for index in range(201):
                (notes / f"note-{index}.md").write_text("Retention review.", encoding="utf-8")

            with self.assertRaisesRegex(InputValidationError, "too many"):
                analyze("retention", Profile("local", str(csv_path), str(notes)))

    def test_too_large_csv_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_bytes(b"\0" * (MAX_CSV_BYTES + 1))
            (notes / "decision.md").write_text("Retention review.", encoding="utf-8")

            with self.assertRaisesRegex(InputValidationError, "CSV is too large"):
                analyze("retention", Profile("local", str(csv_path), str(notes)))

    def test_too_large_document_has_a_specific_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text(
                "date,metric,value\n2026-01-05,retention_rate,0.66\n2026-01-06,retention_rate,0.55\n",
                encoding="utf-8",
            )
            (notes / "decision.md").write_bytes(b"x" * (MAX_DOCUMENT_BYTES + 1))

            with self.assertRaisesRegex(InputValidationError, "document is too large"):
                analyze("retention", Profile("local", str(csv_path), str(notes)))

    def test_zero_baseline_reports_an_undefined_relative_change_and_upward_direction(self):
        rows = [
            MetricRow(date(2026, 1, 1), "activation_rate", 0.0),
            MetricRow(date(2026, 1, 2), "activation_rate", 10.0),
        ]

        signal = _build_signal("activation_rate", rows, default_ruleset())

        self.assertIsNone(signal.change_percent)
        self.assertEqual(signal.direction, "up")
        self.assertIn("相对变化不适用", signal.summary)

    def test_non_finite_metric_values_are_rejected(self):
        for invalid_value in ("nan", "inf", "-inf"):
            with self.subTest(invalid_value=invalid_value), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                csv_path = root / "metrics.csv"
                notes = root / "notes"
                notes.mkdir()
                csv_path.write_text(
                    "date,metric,value\n"
                    "2026-01-05,retention_rate,0.66\n"
                    f"2026-01-06,retention_rate,{invalid_value}\n",
                    encoding="utf-8",
                )
                (notes / "decision.md").write_text("Retention review.", encoding="utf-8")

                with self.assertRaisesRegex(InputValidationError, "finite"):
                    analyze("retention", Profile("local", str(csv_path), str(notes)))

    def test_reversed_english_metric_directions_do_not_confirm_the_condition(self):
        verification = _verify_document_condition(
            Signal("retention_rate", 0.66, 0.55, -16.7, "down", "Retention fell."),
            self._activation_rows(),
            DocumentContext("decision.md", "Retention rises while activation falls.", 4),
            default_ruleset(),
        )

        self.assertNotEqual(verification.status, "confirmed")

    def test_reversed_chinese_metric_directions_do_not_confirm_the_condition(self):
        verification = _verify_document_condition(
            Signal("retention_rate", 0.66, 0.55, -16.7, "down", "留存下降。"),
            self._activation_rows(),
            DocumentContext("decision.md", "激活下降、留存上升。", 4),
            default_ruleset(),
        )

        self.assertNotEqual(verification.status, "confirmed")

    def test_negated_metric_condition_is_not_treated_as_evidence(self):
        verification = _verify_document_condition(
            Signal("retention_rate", 0.66, 0.55, -16.7, "down", "留存下降。"),
            self._activation_rows(),
            DocumentContext("decision.md", "不能说明激活率上升导致留存率下降。", 4),
            default_ruleset(),
        )

        self.assertEqual(verification.status, "not_applicable")

    @staticmethod
    def _activation_rows():
        return [
            MetricRow(date(2026, 1, 1), "activation_rate", 0.40),
            MetricRow(date(2026, 1, 2), "activation_rate", 0.50),
        ]

if __name__ == "__main__":
    unittest.main()
