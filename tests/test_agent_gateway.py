from pathlib import Path
import tempfile
import unittest

from data2doc2data.agents.base import AgentEvent, AgentSession, ProviderStatus
from data2doc2data.agents.gateway import (
    AgentGateway,
    IncompatibleVersion,
    InvalidProviderPayload,
    NotAuthenticated,
    NotInstalled,
    ProviderTimeout,
)


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.connected = False
        self.interrupted = None
        self.closed = False
        self.approval = None
        self.resume_id = None

    def detect(self):
        return ProviderStatus(available=True, connected=self.connected, version="1.0")

    def connect(self):
        self.connected = True

    def create_session(self, workspace, resume_id=None):
        self.resume_id = resume_id
        return resume_id or "upstream-session"

    def stream_turn(self, session, message):
        yield AgentEvent(kind="message.delta", payload={"text": "hello", "private": "ignored"})
        yield {"kind": "turn.completed", "payload": {}, "experimental": "ignored"}

    def decide_approval(self, session, approval_id, approved):
        self.approval = (session.provider_session_id, approval_id, approved)

    def interrupt(self, session):
        self.interrupted = session.provider_session_id

    def close(self):
        self.closed = True


class AgentGatewayTests(unittest.TestCase):
    def test_gateway_normalizes_provider_events(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            gateway = AgentGateway({"fake": provider})
            gateway.connect("fake")
            session = gateway.create_session("fake", Path(directory))

            events = list(gateway.send("fake", session, "hi"))

            self.assertEqual(
                [event.kind for event in events],
                ["message.delta", "turn.completed"],
            )
            self.assertEqual(events[0].payload, {"text": "hello"})

    def test_gateway_supports_resumption_approval_interruption_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider()
            gateway = AgentGateway({"fake": provider})
            gateway.connect("fake")
            session = gateway.create_session("fake", Path(directory), resume_id="prior-thread")

            gateway.decide_approval("fake", session, "approval-1", True)
            gateway.interrupt("fake", session)
            gateway.close()

            self.assertEqual(provider.resume_id, "prior-thread")
            self.assertEqual(provider.approval, ("prior-thread", "approval-1", True))
            self.assertEqual(provider.interrupted, "prior-thread")
            self.assertTrue(provider.closed)

    def test_unknown_provider_raises_typed_not_installed_error(self):
        with self.assertRaises(NotInstalled):
            AgentGateway({}).connect("missing")

    def test_detection_state_maps_to_typed_connection_errors(self):
        cases = (
            (ProviderStatus(False, False), NotInstalled),
            (ProviderStatus(True, False, authenticated=False), NotAuthenticated),
            (ProviderStatus(True, False, compatible=False), IncompatibleVersion),
        )
        for status, expected_error in cases:
            with self.subTest(expected_error=expected_error.__name__):
                provider = FakeProvider()
                provider.detect = lambda status=status: status
                with self.assertRaises(expected_error):
                    AgentGateway({"fake": provider}).connect("fake")

    def test_provider_cannot_replace_the_approved_workspace(self):
        class InvalidSessionProvider(FakeProvider):
            def create_session(self, workspace, resume_id=None):
                return AgentSession("bad", "fake", "upstream", workspace.parent)

        with tempfile.TemporaryDirectory() as directory:
            gateway = AgentGateway({"fake": InvalidSessionProvider()})
            gateway.connect("fake")

            with self.assertRaises(InvalidProviderPayload):
                gateway.create_session("fake", Path(directory))

    def test_missing_required_event_payload_is_rejected(self):
        class InvalidProvider(FakeProvider):
            def stream_turn(self, session, message):
                yield {"kind": "message.delta", "payload": {"unexpected": "value"}}

        with tempfile.TemporaryDirectory() as directory:
            gateway = AgentGateway({"fake": InvalidProvider()})
            gateway.connect("fake")
            session = gateway.create_session("fake", Path(directory))

            with self.assertRaises(InvalidProviderPayload):
                list(gateway.send("fake", session, "hi"))

    def test_provider_timeout_is_normalized(self):
        class SlowProvider(FakeProvider):
            def stream_turn(self, session, message):
                raise TimeoutError("upstream timeout")
                yield

        with tempfile.TemporaryDirectory() as directory:
            gateway = AgentGateway({"fake": SlowProvider()})
            gateway.connect("fake")
            session = gateway.create_session("fake", Path(directory))

            with self.assertRaises(ProviderTimeout):
                list(gateway.send("fake", session, "hi"))


if __name__ == "__main__":
    unittest.main()
