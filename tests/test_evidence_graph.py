import unittest

from data2doc2data.evidence_graph import EvidenceEdge, EvidenceGraph, EvidenceGraphError, EvidenceNode


class EvidenceGraphTests(unittest.TestCase):
    def test_graph_round_trip_supports_auditable_relationships(self):
        source = EvidenceNode("data-1", "data_source", "收入数据", "verified", "dataset-1")
        signal = EvidenceNode("signal-1", "data_signal", "收入下降", "verified", "artifact-1")
        hypothesis = EvidenceNode("hypothesis-1", "hypothesis", "价格影响收入", "pending")
        graph = EvidenceGraph(
            "graph-1",
            (source, signal, hypothesis),
            (
                EvidenceEdge("edge-1", source.node_id, signal.node_id, "derived_from"),
                EvidenceEdge("edge-2", signal.node_id, hypothesis.node_id, "supports"),
            ),
        )

        self.assertEqual(EvidenceGraph.from_dict(graph.to_dict()), graph)

    def test_graph_rejects_dangling_private_reasoning_and_invalid_edges(self):
        source = EvidenceNode("data-1", "data_source", "数据", "verified")
        with self.assertRaisesRegex(EvidenceGraphError, "node type"):
            EvidenceNode("thought-1", "chain_of_thought", "hidden", "pending")
        with self.assertRaisesRegex(EvidenceGraphError, "missing"):
            EvidenceGraph("graph-1", (source,), (EvidenceEdge("edge-1", "data-1", "missing", "supports"),))
        with self.assertRaisesRegex(EvidenceGraphError, "relationship"):
            EvidenceEdge("edge-1", "data-1", "data-2", "causes")


if __name__ == "__main__":
    unittest.main()
