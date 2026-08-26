import unittest

from data2doc2data.agent_protocol import AgentProtocolError, CommunicationEnvelope


class CommunicationEnvelopeTests(unittest.TestCase):
    def test_envelope_round_trip_preserves_causal_delivery_metadata(self):
        envelope = CommunicationEnvelope.create(
            message_id="msg-run-1-2",
            trace_id="run-1",
            causation_id="msg-run-1-1",
            sender="orchestrator",
            receiver="planner.codex",
            attempt=2,
            idempotency_key="plan-run-1-round-2",
            deadline_at="2026-08-26T08:00:10Z",
        )

        self.assertEqual(CommunicationEnvelope.from_dict(envelope.to_dict()), envelope)
        self.assertEqual(envelope.protocol_version, 1)

    def test_envelope_rejects_invalid_identifiers_attempts_and_deadlines(self):
        defaults = {
            "message_id": "msg-1",
            "trace_id": "trace-1",
            "sender": "orchestrator",
            "receiver": "workbench",
            "attempt": 1,
            "idempotency_key": "delivery-1",
        }

        with self.assertRaisesRegex(AgentProtocolError, "sender"):
            CommunicationEnvelope.create(**{**defaults, "sender": "bad sender"})
        with self.assertRaisesRegex(AgentProtocolError, "attempt"):
            CommunicationEnvelope.create(**{**defaults, "attempt": 0})
        with self.assertRaisesRegex(AgentProtocolError, "deadline"):
            CommunicationEnvelope.create(**{**defaults, "deadline_at": "tomorrow"})

    def test_envelope_rejects_unknown_fields_and_protocol_versions(self):
        with self.assertRaisesRegex(AgentProtocolError, "fields"):
            CommunicationEnvelope.from_dict(
                {
                    "protocol_version": 1,
                    "message_id": "msg-1",
                    "trace_id": "trace-1",
                    "causation_id": None,
                    "sender": "orchestrator",
                    "receiver": "workbench",
                    "attempt": 1,
                    "idempotency_key": "delivery-1",
                    "deadline_at": None,
                    "extra": "not-allowed",
                }
            )
        with self.assertRaisesRegex(AgentProtocolError, "protocol_version"):
            CommunicationEnvelope.from_dict(
                {
                    "protocol_version": 2,
                    "message_id": "msg-1",
                    "trace_id": "trace-1",
                    "causation_id": None,
                    "sender": "orchestrator",
                    "receiver": "workbench",
                    "attempt": 1,
                    "idempotency_key": "delivery-1",
                    "deadline_at": None,
                }
            )


if __name__ == "__main__":
    unittest.main()
