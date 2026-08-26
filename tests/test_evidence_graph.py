from pathlib import Path
import tempfile
import unittest

from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
from data2doc2data.artifacts import ArtifactStore
from data2doc2data.diagnostics import AnalyticalArtifact
from data2doc2data.evidence_graph import (
    EvidenceEdge,
    EvidenceGraph,
    EvidenceGraphError,
    EvidenceNode,
    build_cycle_evidence_graph,
)


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

    def test_cycle_artifact_is_an_evidence_node_linked_across_rounds(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ArtifactStore(Path(directory) / "artifacts")
            first = AnalyticalArtifact("artifact-1", "detect_anomalies", "completed", "异常", {}, 8, {})
            second = AnalyticalArtifact(
                "artifact-2", "detect_change_points", "completed", "变化点", {}, 8, {}, source_refs=("artifact-1",)
            )
            store.save_analytical(first)
            store.save_analytical(second)
            cycle = AnalysisCycle.start("cycle-graph")
            cycle = cycle.complete_round(
                AnalysisRound.completed(
                    RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv"}, "检查异常"),
                    ("artifact-1",),
                )
            )
            cycle = cycle.complete_round(
                AnalysisRound.completed(
                    RoundDecision(
                        2,
                        "continue",
                        "detect_change_points",
                        {"metric": "gmv"},
                        "检查变化",
                        prior_artifact_refs=("artifact-1",),
                    ),
                    ("artifact-2",),
                )
            )

            graph = build_cycle_evidence_graph(cycle, store)

        nodes = {node.node_id: node for node in graph.nodes}
        self.assertEqual(nodes["artifact-1"].kind, "analytical_artifact")
        self.assertEqual(nodes["artifact-2"].artifact_ref, "artifact-2")
        self.assertTrue(any(edge.source == "artifact-1" and edge.target == "artifact-2" for edge in graph.edges))


if __name__ == "__main__":
    unittest.main()
