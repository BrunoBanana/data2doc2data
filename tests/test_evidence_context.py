import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis import analyze
from data2doc2data.config import Profile
from data2doc2data.evidence_context import EvidenceContextBuilder, build_source_profile


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


class EvidenceSnapshotTests(unittest.TestCase):
    def test_data_size_question_gets_compact_local_facts_without_raw_csv_rows(self):
        snapshot = EvidenceContextBuilder().build("数据有多少？", Profile.demo())

        self.assertEqual(snapshot.summary.record_count, 12)
        self.assertEqual(snapshot.summary.metric_count, 2)
        self.assertEqual(snapshot.summary.date_count, 6)
        self.assertEqual(snapshot.summary.document_count, 1)
        self.assertFalse(snapshot.summary.compressed)
        self.assertIn("记录数: 12", snapshot.envelope)
        self.assertIn("指标数: 2", snapshot.envelope)
        self.assertIn("日期数: 6", snapshot.envelope)
        self.assertNotIn("2026-01-05,retention_rate,0.66", snapshot.envelope)
        self.assertNotIn("2026-01-05,activation_rate,0.42", snapshot.envelope)
        prompt = snapshot.render_prompt("数据有多少？")
        self.assertIn("USER MESSAGE\n数据有多少？", prompt)

    def test_matching_analysis_is_included_but_a_stale_analysis_is_not(self):
        profile = Profile.demo()
        result = analyze("留存为什么下降？", profile)
        fingerprint = build_source_profile(profile).fingerprint
        builder = EvidenceContextBuilder()

        current = builder.build(
            "解释当前结论",
            profile,
            analysis=result,
            analysis_source_fingerprint=fingerprint,
        )
        stale = builder.build(
            "解释当前结论",
            profile,
            analysis=result,
            analysis_source_fingerprint="0" * 64,
        )

        self.assertIn("DETERMINISTIC FINDINGS", current.envelope)
        self.assertIn(result.provenance.analysis_id, current.envelope)
        self.assertNotIn("DETERMINISTIC FINDINGS", stale.envelope)

    def test_small_budget_drops_excerpts_and_marks_visible_compression(self):
        snapshot = EvidenceContextBuilder(max_context_bytes=800).build(
            "留存为什么下降？",
            Profile.demo(),
        )

        self.assertTrue(snapshot.summary.compressed)
        self.assertEqual(snapshot.summary.excerpt_count, 0)
        self.assertIn("记录数: 12", snapshot.envelope)
        self.assertLessEqual(len(snapshot.envelope.encode("utf-8")), 800)

    def test_snapshot_id_is_stable_for_the_same_source_and_question(self):
        builder = EvidenceContextBuilder()

        first = builder.build("数据有多少？", Profile.demo())
        second = builder.build("数据有多少？", Profile.demo())

        self.assertEqual(first.summary.snapshot_id, second.summary.snapshot_id)


if __name__ == "__main__":
    unittest.main()
