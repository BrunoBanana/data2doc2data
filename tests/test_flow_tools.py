import tempfile
from pathlib import Path
import unittest

from data2doc2data.flow_tools import LocalAnalysisTools


class LocalAnalysisToolsTests(unittest.TestCase):
    def test_inspect_profile_query_and_claim_tools_return_bounded_summaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            data.write_text(
                "date,metric,value\n"
                "2026-01-01,revenue,10\n"
                "2026-01-08,revenue,14\n",
                encoding="utf-8",
            )
            document = root / "review.md"
            document.write_text("# Review\n主张：revenue 上升可能来自新渠道。", encoding="utf-8")
            tools = LocalAnalysisTools((root,))

            inspected = tools.inspect_sources((data, document))
            profiled = tools.profile_data(data, "dataset-test")
            queried = tools.query_data(data, "dataset-test", "revenue")
            claims = tools.extract_claims((document,), "corpus-test")
            aligned = tools.align_evidence(data, "dataset-test", (document,), "corpus-test")
            verified = tools.test_hypothesis(
                data,
                "dataset-test",
                {
                    "clauses": [{"metric": "revenue", "direction": "up"}],
                    "source": "agent_proposed",
                },
            )

        self.assertEqual(inspected.status, "completed")
        self.assertEqual(inspected.summary["modalities"], ["data", "text"])
        self.assertEqual(profiled.summary["row_count"], 2)
        self.assertEqual(queried.summary["metric"], "revenue")
        self.assertEqual(queried.summary["minimum"], 10.0)
        self.assertEqual(claims.summary["claim_count"], 1)
        self.assertEqual(aligned.summary["alignment_count"], 1)
        self.assertEqual(verified.summary["status"], "confirmed")
        for result in (inspected, profiled, queried, claims, aligned, verified):
            self.assertNotIn("raw_rows", result.summary)


if __name__ == "__main__":
    unittest.main()
