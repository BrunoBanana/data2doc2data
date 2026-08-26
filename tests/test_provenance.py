import unittest

from data2doc2data.provenance import SourceRef, build_provenance


class ProvenanceTests(unittest.TestCase):
    def test_identical_sources_and_parameters_have_a_stable_analysis_id(self):
        sources = (
            SourceRef(path="metrics.csv", sha256="a" * 64, rows=(2, 3)),
            SourceRef(path="strategy.md", sha256="b" * 64, start_line=4, end_line=6),
        )

        first = build_provenance(sources, {"metric": "retention_rate"})
        second = build_provenance(sources, {"metric": "retention_rate"})

        self.assertEqual(first.analysis_id, second.analysis_id)
        self.assertRegex(first.analysis_id, r"^[0-9a-f]{64}$")
        self.assertTrue(first.engine_version)

    def test_analysis_id_changes_when_parameters_change(self):
        sources = (SourceRef(path="metrics.csv", sha256="a" * 64, rows=(2, 3)),)

        first = build_provenance(sources, {"threshold": 1.0})
        second = build_provenance(sources, {"threshold": 2.0})

        self.assertNotEqual(first.analysis_id, second.analysis_id)

    def test_provenance_copies_mutable_parameters(self):
        parameters = {"metrics": ["retention_rate"]}

        provenance = build_provenance((), parameters)
        parameters["metrics"].append("activation_rate")

        self.assertEqual(provenance.parameters, {"metrics": ["retention_rate"]})


if __name__ == "__main__":
    unittest.main()
