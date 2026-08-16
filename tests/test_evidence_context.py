import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.config import Profile
from data2doc2data.evidence_context import build_source_profile


class SourceProfileTests(unittest.TestCase):
    def test_default_demo_reports_its_exact_evidence_scale_without_raw_values(self):
        profile = build_source_profile(Profile.demo())

        self.assertEqual(profile.mode, "demo")
        self.assertEqual(profile.label, "增长质量预警")
        self.assertTrue(profile.synthetic)
        self.assertEqual(profile.record_count, 12)
        self.assertEqual(profile.metrics, ("activation_rate", "retention_rate"))
        self.assertEqual(
            profile.observation_dates,
            (
                "2026-01-05",
                "2026-01-12",
                "2026-01-19",
                "2026-01-26",
                "2026-02-02",
                "2026-02-09",
            ),
        )
        self.assertEqual(profile.document_count, 1)
        self.assertEqual(len(profile.source_hashes), 2)
        self.assertEqual(len(profile.fingerprint), 64)
        serialized = json.dumps(profile.to_dict(), ensure_ascii=False)
        self.assertNotIn("0.66", serialized)
        self.assertNotIn("0.42", serialized)

    def test_local_profile_uses_validated_files_and_changes_with_source_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "customer-health.csv"
            docs = root / "docs"
            docs.mkdir()
            csv_path.write_text(
                "date,metric,value\n"
                "2026-01-01,health_score,0.5\n"
                "2026-01-08,health_score,0.6\n",
                encoding="utf-8",
            )
            (docs / "decision.md").write_text("# Decision\n\nHealth improved.\n", encoding="utf-8")
            local = Profile("local", str(csv_path), str(docs))

            first = build_source_profile(local)
            csv_path.write_text(
                "date,metric,value\n"
                "2026-01-01,health_score,0.5\n"
                "2026-01-08,health_score,0.6\n"
                "2026-01-15,health_score,0.7\n",
                encoding="utf-8",
            )
            second = build_source_profile(local)

        self.assertEqual(first.label, "customer-health.csv")
        self.assertFalse(first.synthetic)
        self.assertEqual(first.record_count, 2)
        self.assertEqual(first.metrics, ("health_score",))
        self.assertEqual(first.document_count, 1)
        self.assertEqual(second.record_count, 3)
        self.assertNotEqual(first.fingerprint, second.fingerprint)


if __name__ == "__main__":
    unittest.main()
