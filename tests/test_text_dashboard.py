from pathlib import Path
import tempfile
import unittest

from data2doc2data.documents import build_document_corpus
from data2doc2data.text_dashboard import build_text_dashboard


class TextDashboardTests(unittest.TestCase):
    def test_dashboard_extracts_bounded_topics_entities_and_pending_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "strategy.md"
            path.write_text(
                "# 收入策略\n\n主张：华东区收入目标为 120 万元。\n\n# 风险\n\n主张：华东区收入目标为 100 万元。\n",
                encoding="utf-8",
            )
            dashboard = build_text_dashboard(build_document_corpus((path,), "corpus-1"))

        self.assertEqual(dashboard.document_count, 1)
        self.assertIn("收入", dashboard.topics)
        self.assertIn("华东区", dashboard.entities)
        self.assertEqual(len(dashboard.claims), 2)
        self.assertTrue(all(claim.status == "pending" for claim in dashboard.claims))
        self.assertTrue(all(claim.citation.sha256 for claim in dashboard.claims))
        self.assertEqual(dashboard.claims[0].conflicts_with, (dashboard.claims[1].claim_id,))
        self.assertLessEqual(len(dashboard.topics), 20)
        self.assertLessEqual(len(dashboard.entities), 50)

    def test_claims_never_become_deterministic_conclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "claim.txt"
            path.write_text("主张：留存下降由价格调整导致。", encoding="utf-8")
            dashboard = build_text_dashboard(build_document_corpus((path,), "corpus-1"))

        self.assertEqual(dashboard.claims[0].status, "pending")
        self.assertNotIn("conclusion", dashboard.to_dict())

    def test_extracts_structured_claim_from_ordinary_business_prose(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.md"
            path.write_text("五月直播渠道退款率明显上升。", encoding="utf-8")
            dashboard = build_text_dashboard(build_document_corpus((path,), "corpus-structured"))

        self.assertEqual(len(dashboard.claims), 1)
        claim = dashboard.claims[0]
        self.assertEqual(claim.metric_refs, ("refund_rate",))
        self.assertEqual(claim.direction, "up")
        self.assertEqual(claim.time_refs, ("五月",))
        self.assertIn("直播", claim.entities)
        self.assertEqual(claim.citation.start_line, 1)

    def test_negated_direction_is_marked_ambiguous_instead_of_inverted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.md"
            path.write_text("六月留存率并未下降。", encoding="utf-8")
            dashboard = build_text_dashboard(build_document_corpus((path,), "corpus-negated"))

        self.assertEqual(dashboard.claims[0].metric_refs, ("retention_rate",))
        self.assertEqual(dashboard.claims[0].direction, "ambiguous")
        self.assertTrue(dashboard.claims[0].negated)


if __name__ == "__main__":
    unittest.main()
