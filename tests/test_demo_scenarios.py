from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.demo_scenarios import (
    DEFAULT_DEMO_SCENARIO,
    DemoScenarioCatalog,
    DemoScenarioError,
)


SCENARIOS = [
    {
        "id": "growth-quality-alert",
        "label": "增长质量预警",
        "summary": "激活改善，但留存下降。",
        "suggested_question": "留存为什么下降？",
        "learning_objective": "展示获得数据支持的结论。",
        "expected_validation": "supported",
    },
    {
        "id": "strategy-data-conflict",
        "label": "策略与数据冲突",
        "summary": "策略假设与指标方向相反。",
        "suggested_question": "策略假设得到支持了吗？",
        "learning_objective": "展示系统识别矛盾证据。",
        "expected_validation": "contradicted",
    },
    {
        "id": "insufficient-evidence",
        "label": "证据不足",
        "summary": "缺少验证所需的第二指标。",
        "suggested_question": "现有证据足够吗？",
        "learning_objective": "展示系统拒绝强行下结论。",
        "expected_validation": "insufficient",
    },
]


class DemoScenarioCatalogTests(unittest.TestCase):
    def test_package_catalog_has_stable_order_and_default(self):
        catalog = DemoScenarioCatalog.load()

        self.assertEqual(DEFAULT_DEMO_SCENARIO, "growth-quality-alert")
        self.assertEqual(catalog.default.id, DEFAULT_DEMO_SCENARIO)
        self.assertEqual(
            [scenario.id for scenario in catalog.list()],
            ["growth-quality-alert", "strategy-data-conflict", "insufficient-evidence"],
        )

    def test_metadata_is_immutable_and_public_payload_contains_no_paths(self):
        catalog = self.make_catalog()
        scenario = catalog.default

        with self.assertRaises(FrozenInstanceError):
            scenario.label = "changed"
        payload = scenario.to_dict()
        self.assertEqual(payload["id"], "growth-quality-alert")
        self.assertFalse(any("path" in key for key in payload))
        self.assertNotIn(str(catalog.root), json.dumps(payload, ensure_ascii=False))

    def test_sources_are_derived_from_the_fixed_catalog_root(self):
        catalog = self.make_catalog()

        metrics_path, document_path = catalog.sources("growth-quality-alert")

        expected_root = catalog.root / "growth-quality-alert"
        self.assertEqual(metrics_path, expected_root / "metrics.csv")
        self.assertEqual(document_path, expected_root / "strategy.md")

    def test_unknown_and_path_like_ids_are_rejected(self):
        catalog = self.make_catalog()

        for scenario_id in ("missing", "../../customer-data", "growth quality"):
            with self.subTest(scenario_id=scenario_id):
                with self.assertRaises(DemoScenarioError):
                    catalog.get(scenario_id)

    def test_catalog_rejects_path_fields_and_unknown_metadata(self):
        for extra_field in ("metrics_path", "document_path", "unexpected"):
            with self.subTest(extra_field=extra_field):
                scenarios = [dict(SCENARIOS[0], **{extra_field: "/tmp/private"})]
                with self.assertRaisesRegex(DemoScenarioError, "fields"):
                    self.make_catalog(scenarios=scenarios)

    def test_catalog_rejects_duplicate_ids_and_an_unknown_default(self):
        with self.assertRaisesRegex(DemoScenarioError, "duplicate"):
            self.make_catalog(scenarios=[SCENARIOS[0], SCENARIOS[0]])
        with self.assertRaisesRegex(DemoScenarioError, "default"):
            self.make_catalog(default="missing")

    def test_catalog_requires_exact_scalar_types(self):
        with self.assertRaisesRegex(DemoScenarioError, "version"):
            self.make_catalog(version=True)
        invalid_scenario = dict(SCENARIOS[0], expected_validation=["supported"])
        with self.assertRaisesRegex(DemoScenarioError, "validation"):
            self.make_catalog(scenarios=[invalid_scenario])

    def test_sources_fail_clearly_when_a_required_file_is_missing(self):
        catalog = self.make_catalog()
        (catalog.root / "growth-quality-alert" / "strategy.md").unlink()

        with self.assertRaisesRegex(DemoScenarioError, "strategy.md"):
            catalog.sources("growth-quality-alert")

    def test_sources_reject_a_file_symlink_outside_the_catalog(self):
        catalog = self.make_catalog()
        metrics_path = catalog.root / "growth-quality-alert" / "metrics.csv"
        outside_path = catalog.root.parent / "private.csv"
        outside_path.write_text("secret\n", encoding="utf-8")
        metrics_path.unlink()
        metrics_path.symlink_to(outside_path)

        with self.assertRaisesRegex(DemoScenarioError, "outside"):
            catalog.sources("growth-quality-alert")

    def make_catalog(self, scenarios=None, default="growth-quality-alert", version=1):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        selected_scenarios = scenarios or SCENARIOS
        (root / "catalog.json").write_text(
            json.dumps(
                {"version": version, "default": default, "scenarios": selected_scenarios},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        for scenario in selected_scenarios:
            scenario_root = root / scenario["id"]
            scenario_root.mkdir(parents=True, exist_ok=True)
            (scenario_root / "metrics.csv").write_text("date,metric,value\n", encoding="utf-8")
            (scenario_root / "strategy.md").write_text("# 合成演示\n", encoding="utf-8")
        return DemoScenarioCatalog.load(root)


if __name__ == "__main__":
    unittest.main()
