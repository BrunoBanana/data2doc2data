import unittest

from data2doc2data.agent_protocol import CommunicationEnvelope
from data2doc2data.run_events import RunEvent, RunEventError, validate_event_stream


class RunEventContractTests(unittest.TestCase):
    def test_flow_events_cover_live_graph_tool_and_knowledge_lifecycle(self):
        kinds = (
            "run.interrupted",
            "plan.created",
            "plan.revised",
            "step.added",
            "tool.started",
            "tool.progress",
            "tool.result",
            "tool.failed",
            "node.added",
            "node.updated",
            "edge.added",
            "edge.activated",
            "conflict.detected",
            "knowledge.candidate",
            "knowledge.verified",
            "knowledge.superseded",
            "dashboard.updated",
            "report.generated",
        )

        events = tuple(
            RunEvent.create(
                "run-live",
                sequence,
                kind,
                "flow",
                {"node_id": "node-1", "progress": sequence},
            )
            for sequence, kind in enumerate(kinds, 1)
        )

        self.assertEqual(validate_event_stream(events), events)

    def test_events_cover_persisted_analysis_cycle_lifecycle(self):
        kinds = (
            "cycle.started",
            "round.planned",
            "round.started",
            "artifact.created",
            "round.completed",
            "cycle.checkpointed",
            "planner.waiting",
            "planner.resumed",
            "cycle.completed",
        )
        events = tuple(
            RunEvent.create("run-cycle", index, kind, "cycle", {"round": min(index, 3)})
            for index, kind in enumerate(kinds, 1)
        )

        self.assertEqual(validate_event_stream(events), events)
        self.assertTrue(all(event.contract_version == 1 for event in events))

    def test_event_round_trip_has_stable_sequence_and_artifact_references(self):
        event = RunEvent.create(
            run_id="run-1",
            sequence=1,
            kind="compute.result.created",
            phase="compute",
            summary={"metric": "revenue", "value": 42, "row_count": 12},
            artifact_refs=("artifact-1",),
            now="2026-08-23T08:01:00Z",
        )

        restored = RunEvent.from_dict(event.to_dict())

        self.assertEqual(restored, event)
        self.assertEqual(restored.contract_version, 1)
        self.assertEqual(restored.communication.trace_id, "run-1")
        self.assertEqual(restored.communication.message_id, "msg-run-1-1")

    def test_legacy_event_without_communication_gets_a_deterministic_envelope(self):
        payload = RunEvent.create("run-legacy", 1, "run.started", "setup", {}).to_dict()
        payload.pop("communication")

        first = RunEvent.from_dict(payload)
        second = RunEvent.from_dict(payload)

        self.assertEqual(first.communication, second.communication)
        self.assertEqual(first.communication.sender, "orchestrator")
        self.assertEqual(first.communication.receiver, "workbench")

    def test_default_envelope_supports_the_longest_valid_run_identifier(self):
        event = RunEvent.create("r" * 200, 1, "run.started", "setup", {})

        self.assertLessEqual(len(event.communication.message_id), 200)
        self.assertLessEqual(len(event.communication.idempotency_key), 200)

    def test_stream_rejects_duplicate_message_ids_and_forward_causation(self):
        shared = CommunicationEnvelope.create(
            message_id="msg-shared",
            trace_id="run-1",
            sender="orchestrator",
            receiver="workbench",
            attempt=1,
            idempotency_key="delivery-shared",
        )
        first = RunEvent.create("run-1", 1, "run.started", "setup", {}, communication=shared)
        duplicate = RunEvent.create("run-1", 2, "run.completed", "finish", {}, communication=shared)

        with self.assertRaisesRegex(RunEventError, "message_id"):
            validate_event_stream((first, duplicate))

        forward = CommunicationEnvelope.create(
            message_id="msg-run-1-2",
            trace_id="run-1",
            causation_id="msg-run-1-3",
            sender="orchestrator",
            receiver="workbench",
            attempt=1,
            idempotency_key="delivery-2",
        )
        with self.assertRaisesRegex(RunEventError, "causation"):
            validate_event_stream((first, RunEvent.create("run-1", 2, "run.completed", "finish", {}, communication=forward)))

    def test_event_rejects_raw_records_and_oversized_summaries(self):
        with self.assertRaisesRegex(RunEventError, "raw"):
            RunEvent.create(
                run_id="run-1",
                sequence=1,
                kind="data.profiled",
                phase="profile",
                summary={"raw_rows": [{"secret": "value"}]},
            )
        with self.assertRaisesRegex(RunEventError, "bounded"):
            RunEvent.create(
                run_id="run-1",
                sequence=1,
                kind="data.profiled",
                phase="profile",
                summary={"message": "x" * 4097},
            )

        with self.assertRaisesRegex(RunEventError, "raw"):
            RunEvent.create(
                run_id="run-1",
                sequence=1,
                kind="data.profiled",
                phase="profile",
                summary={"result": {"records": [{"secret": "value"}]}},
            )

    def test_event_summary_is_detached_from_mutable_input(self):
        source = {"result": {"count": 12}}
        event = RunEvent.create("run-1", 1, "data.profiled", "profile", source)

        source["result"]["count"] = 99

        self.assertEqual(event.to_dict()["summary"], {"result": {"count": 12}})

    def test_event_rejects_unknown_kinds_and_invalid_sequences(self):
        with self.assertRaisesRegex(RunEventError, "kind"):
            RunEvent.create(
                run_id="run-1",
                sequence=1,
                kind="thought.private",
                phase="reasoning",
                summary={},
            )
        with self.assertRaisesRegex(RunEventError, "sequence"):
            RunEvent.create(
                run_id="run-1",
                sequence=0,
                kind="run.started",
                phase="setup",
                summary={},
            )

    def test_stream_requires_one_run_and_contiguous_monotonic_sequences(self):
        first = RunEvent.create("run-1", 1, "run.started", "setup", {})
        second = RunEvent.create("run-1", 2, "data.profiled", "profile", {"rows": 12})

        self.assertEqual(validate_event_stream((first, second)), (first, second))
        with self.assertRaisesRegex(RunEventError, "contiguous"):
            validate_event_stream((first, RunEvent.create("run-1", 3, "run.completed", "finish", {})))
        with self.assertRaisesRegex(RunEventError, "same run"):
            validate_event_stream((first, RunEvent.create("run-2", 2, "run.completed", "finish", {})))


if __name__ == "__main__":
    unittest.main()
