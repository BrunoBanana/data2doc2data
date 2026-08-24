import json
import tempfile
from pathlib import Path
import unittest

from data2doc2data.artifacts import ArtifactStore
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

    def test_deep_tool_persists_full_artifact_and_returns_bounded_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "metrics.csv"
            data.write_text(
                "date,metric,value,channel\n"
                "2026-01-01,gmv,10,直播\n"
                "2026-01-02,gmv,10,直播\n"
                "2026-01-03,gmv,11,货架\n"
                "2026-01-04,gmv,10,货架\n"
                "2026-01-05,gmv,50,直播\n",
                encoding="utf-8",
            )
            artifact_store = ArtifactStore(root / "artifacts")
            tools = LocalAnalysisTools((root,), artifact_store=artifact_store)

            result = tools.detect_anomalies(data, "snapshot-1", metric="gmv", window=3, threshold=4)
            persisted = artifact_store.load(result.artifact_refs[0])
            projection = result.agent_projection()
            encoded = json.dumps(projection, ensure_ascii=False)

        self.assertEqual(result.status, "completed")
        self.assertEqual(persisted["kind"], "analytical")
        self.assertEqual(persisted["payload"]["method"], "detect_anomalies")
        self.assertLessEqual(len(encoded.encode("utf-8")), 8192)
        self.assertNotIn("rows", encoded.lower())
        self.assertNotIn(str(data), encoded)

    def test_artifact_store_rejects_mutating_an_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            store.save("artifact-fixed", "fixture", {"value": 1})

            with self.assertRaisesRegex(ValueError, "immutable"):
                store.save("artifact-fixed", "fixture", {"value": 2})


if __name__ == "__main__":
    unittest.main()
