from pathlib import Path
from queue import Queue
import tempfile
import unittest

from data2doc2data.agents._shared import (
    emit_provider_error,
    minimal_environment,
    required_text,
    validate_session,
)
from data2doc2data.agents.base import AgentSession
from data2doc2data.agents.gateway import InvalidProviderPayload


class EmitProviderErrorTests(unittest.TestCase):
    def test_broadcasts_to_every_active_queue(self):
        first = Queue()
        second = Queue()
        event_queues = {"a": first, "b": second}

        emit_provider_error(event_queues, "provider died", "providerExited")

        for queue in (first, second):
            event = queue.get_nowait()
            self.assertEqual(event.kind, "provider.error")
            self.assertEqual(event.payload, {"message": "provider died", "code": "providerExited"})


class ValidateSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name).resolve()

    def test_matching_session_passes(self):
        session = AgentSession("id-1", "codex", "provider-session", self.workspace)

        validate_session("codex", session, self.workspace, {"provider-session": Queue()})

    def test_foreign_provider_is_rejected(self):
        session = AgentSession("id-1", "workbuddy", "provider-session", self.workspace)

        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_session("codex", session, self.workspace, {"provider-session": Queue()})

    def test_unknown_provider_session_is_rejected(self):
        session = AgentSession("id-1", "codex", "missing-session", self.workspace)

        with self.assertRaisesRegex(ValueError, "not active"):
            validate_session("codex", session, self.workspace, {})


class MinimalEnvironmentTests(unittest.TestCase):
    def test_returns_only_allowed_keys_with_extras(self):
        environment = minimal_environment("CODEX_HOME")

        self.assertIn("PATH", environment)
        self.assertNotIn("CODEX_HOME", environment)  # not set in the test process
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)

    def test_missing_keys_are_omitted(self):
        environment = minimal_environment("__NOT_SET_D2D2D__")

        self.assertNotIn("__NOT_SET_D2D2D__", environment)


class RequiredTextTests(unittest.TestCase):
    def test_returns_the_string_field(self):
        self.assertEqual(required_text("codex", {"delta": "hi"}, "delta"), "hi")

    def test_missing_field_is_rejected(self):
        with self.assertRaises(InvalidProviderPayload):
            required_text("codex", {}, "delta")

    def test_non_string_field_is_rejected(self):
        with self.assertRaises(InvalidProviderPayload):
            required_text("codex", {"delta": 123}, "delta")

    def test_empty_string_is_accepted_when_nonempty_is_false(self):
        self.assertEqual(required_text("codex", {"delta": ""}, "delta"), "")

    def test_empty_string_is_rejected_when_nonempty_is_true(self):
        with self.assertRaises(InvalidProviderPayload):
            required_text("workbuddy", {"delta": ""}, "delta", nonempty=True)


if __name__ == "__main__":
    unittest.main()
