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


if __name__ == "__main__":
    unittest.main()
