from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.flagship_cases import FlagshipCaseCatalog, FlagshipCaseError


class FlagshipCaseCatalogTest(unittest.TestCase):
    def test_built_in_catalog_has_two_rich_cases_with_locked_semantics(self):
        catalog = FlagshipCaseCatalog.load()

        self.assertEqual(
            [case.id for case in catalog.list()],
            ["saas-growth-retention", "retail-promotion-fulfillment"],
        )
        saas = catalog.package("saas-growth-retention")
        retail = catalog.package("retail-promotion-fulfillment")
        self.assertEqual((saas.case.record_count, saas.case.metric_count, saas.case.document_count), (208, 8, 4))
        self.assertEqual((retail.case.record_count, retail.case.metric_count, retail.case.document_count), (260, 10, 5))
        self.assertLess(
            self._value(saas.metrics_path, "retention_8w", "2026-06-29"),
            self._value(saas.metrics_path, "retention_8w", "2026-01-05"),
        )
        self.assertGreater(
            self._value(saas.metrics_path, "trial_signups", "2026-06-29"),
            self._value(saas.metrics_path, "trial_signups", "2026-01-05"),
        )
        self.assertGreater(
            self._value(retail.metrics_path, "gmv", "2026-05-04"), self._value(retail.metrics_path, "gmv", "2026-02-02")
        )
        self.assertLess(
            self._value(retail.metrics_path, "gross_margin_rate", "2026-05-04"),
            self._value(retail.metrics_path, "gross_margin_rate", "2026-02-02"),
        )
        for package in (saas, retail):
            hypotheses = json.loads(package.hypotheses_path.read_text(encoding="utf-8"))
            expected = json.loads(package.expected_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(hypotheses["hypotheses"]), 3)
            self.assertGreaterEqual(len(expected["outcomes"]), 3)

    def test_catalog_exposes_a_complete_synthetic_case_package(self):
        catalog = self._catalog_with_valid_package()

        self.assertEqual([case.id for case in catalog.list()], ["complete-case"])
        for case in catalog.list():
            package = catalog.package(case.id)
            self.assertGreaterEqual(case.record_count, 200)
            self.assertGreaterEqual(case.metric_count, 8)
            self.assertGreaterEqual(case.document_count, 4)
            self.assertTrue(case.synthetic)
            self.assertTrue(package.metrics_path.is_file())
            self.assertTrue(all(path.is_file() for path in package.document_paths))
            self.assertTrue(package.rules_path.is_file())
            self.assertTrue(package.hypotheses_path.is_file())
            self.assertTrue(package.expected_path.is_file())
            self.assertTrue(package.demo_flow_path.is_file())
            manifest = json.loads(package.demo_flow_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["runner"], "demo")
            self.assertTrue(manifest["use_bundled_hypotheses"])

    def test_rejects_unknown_or_malformed_case_ids(self):
        catalog = self._catalog_with_valid_package()

        with self.assertRaisesRegex(FlagshipCaseError, "invalid flagship case ID"):
            catalog.package("../escape")
        with self.assertRaisesRegex(FlagshipCaseError, "unknown flagship case ID"):
            catalog.package("not-present")

    def test_rejects_duplicate_metric_records(self):
        root, cleanup = self._valid_root()
        self.addCleanup(cleanup.cleanup)
        metrics_path = root / "complete-case" / "metrics.csv"
        rows = list(csv.DictReader(metrics_path.read_text(encoding="utf-8").splitlines()))
        with metrics_path.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["date", "metric", "value", "segment", "unit"])
            writer.writerow(rows[0])

        with self.assertRaisesRegex(FlagshipCaseError, "duplicate metric record"):
            FlagshipCaseCatalog.load(root)

    def test_rejects_document_symlinks_that_escape_the_package(self):
        root, cleanup = self._valid_root()
        self.addCleanup(cleanup.cleanup)
        outside = root.parent / "outside.md"
        outside.write_text("not part of the case", encoding="utf-8")
        linked = root / "complete-case" / "documents" / "strategy.md"
        linked.unlink()
        linked.symlink_to(outside)

        with self.assertRaisesRegex(FlagshipCaseError, "outside the flagship case package"):
            FlagshipCaseCatalog.load(root)

    def test_rejects_unexpected_companion_json_fields(self):
        root, cleanup = self._valid_root()
        self.addCleanup(cleanup.cleanup)
        (root / "complete-case" / "hypotheses.json").write_text(
            json.dumps({"version": 1, "hypotheses": [], "private_path": "/tmp/source.csv"}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(FlagshipCaseError, "hypotheses fields are invalid"):
            FlagshipCaseCatalog.load(root)

    def test_rejects_invalid_declarative_rules(self):
        root, cleanup = self._valid_root()
        self.addCleanup(cleanup.cleanup)
        (root / "complete-case" / "rules.json").write_text(
            json.dumps({"version": 1, "metrics": {}, "rules": []}),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(FlagshipCaseError, "rules are invalid"):
            FlagshipCaseCatalog.load(root)

    def _catalog_with_valid_package(self) -> FlagshipCaseCatalog:
        root, cleanup = self._valid_root()
        self.addCleanup(cleanup.cleanup)
        return FlagshipCaseCatalog.load(root)

    def _valid_root(self) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
        cleanup = tempfile.TemporaryDirectory()
        root = Path(cleanup.name) / "cases"
        case_root = root / "complete-case"
        documents = case_root / "documents"
        documents.mkdir(parents=True)
        (root / "catalog.json").write_text(
            json.dumps({"version": 1, "cases": ["complete-case"]}),
            encoding="utf-8",
        )
        document_names = ["strategy.md", "research.md", "experiment.md", "glossary.md"]
        for name in document_names:
            (documents / name).write_text("# 合成材料\n\n这是用于测试的合成文档。\n", encoding="utf-8")
        metrics = [f"metric_{index}" for index in range(8)]
        with (case_root / "metrics.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["date", "metric", "value", "segment", "unit"])
            writer.writeheader()
            for week in range(25):
                for index, metric in enumerate(metrics):
                    writer.writerow(
                        {
                            "date": f"2026-0{1 + week // 9}-{1 + (week % 9) * 3:02d}",
                            "metric": metric,
                            "value": str(100 + week + index),
                            "segment": "all",
                            "unit": "count",
                        }
                    )
        metadata = {
            "id": "complete-case",
            "title": "完整合成案例",
            "summary": "用于验证完整案例契约。",
            "business_question": "指标变化由什么驱动？",
            "learning_objective": "学习从数据到证据的完整流程。",
            "synthetic": True,
            "record_count": 200,
            "metrics": metrics,
            "documents": document_names,
            "time_range": {"start": "2026-01-01", "end": "2026-03-14", "grain": "week"},
        }
        (case_root / "case.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        (case_root / "rules.json").write_text(
            json.dumps({"version": 1, "metrics": {metric: {} for metric in metrics}, "rules": []}),
            encoding="utf-8",
        )
        (case_root / "hypotheses.json").write_text(json.dumps({"version": 1, "hypotheses": []}), encoding="utf-8")
        (case_root / "expected.json").write_text(json.dumps({"version": 1, "outcomes": []}), encoding="utf-8")
        (case_root / "demo-flow.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "runner": "demo",
                    "use_bundled_hypotheses": True,
                    "stages": ["inspect", "profile", "extract", "align", "verify", "report"],
                }
            ),
            encoding="utf-8",
        )
        return root, cleanup

    @staticmethod
    def _value(path: Path, metric: str, when: str) -> float:
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if row["metric"] == metric and row["date"] == when:
                    return float(row["value"])
        raise AssertionError(f"missing {metric} at {when}")


if __name__ == "__main__":
    unittest.main()
