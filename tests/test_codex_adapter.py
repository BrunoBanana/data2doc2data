from pathlib import Path
import sys
import tempfile
import unittest

from data2doc2data.agents.codex import CodexProvider
from data2doc2data.agents.gateway import AgentGateway
from data2doc2data.analysis import analyze
from data2doc2data.config import Profile


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "codex_app_server"
FAKE_SERVER = FIXTURE_ROOT / "fake_app_server.py"


class CodexAdapterTests(unittest.TestCase):
    def make_provider(self, workspace, *server_args, timeout=2.0, event_timeout=None):
        return CodexProvider(
            workspace=workspace,
            executable=sys.executable,
            version_command=(sys.executable, str(FAKE_SERVER), "--version"),
            app_server_command=(sys.executable, "-u", str(FAKE_SERVER), *server_args),
            request_timeout=timeout,
            event_timeout=event_timeout,
        )

    def test_fake_app_server_turn_is_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            provider = self.make_provider(workspace)

            status = provider.detect()
            self.assertTrue(status.available)
            self.assertFalse(status.connected)
            gateway = AgentGateway({"codex": provider})
            gateway.connect("codex")
            session = gateway.create_session("codex", workspace)
            events = list(gateway.send("codex", session, "hello"))

            self.assertEqual(
                [event.kind for event in events],
                ["message.delta", "approval.request", "turn.completed"],
            )
            self.assertEqual(events[0].payload["text"], "hello from codex")
            self.assertEqual(events[1].payload["request_id"], "approval-1")
            self.assertEqual(events[1].payload["command"], "git status")
            gateway.decide_approval("codex", session, "approval-1", True)
            gateway.interrupt("codex", session)
            gateway.close()

    def test_process_crash_emits_provider_error_and_does_not_break_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            provider = self.make_provider(workspace, "--crash-on-turn")
            provider.connect()
            session_id = provider.create_session(workspace)
            from data2doc2data.agents.base import AgentSession

            session = AgentSession("local-1", "codex", session_id, workspace.resolve())
            events = list(provider.stream_turn(session, "crash"))

            self.assertEqual(events[-1].kind, "provider.error")
            self.assertEqual(analyze("retention", Profile.demo()).signal.metric, "retention_rate")
            provider.close()

    def test_initialize_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = self.make_provider(Path(directory), "--hang-on-initialize", timeout=0.05)

            with self.assertRaises(TimeoutError):
                provider.connect()
            provider.close()

    def test_turn_event_timeout_is_separate_from_rpc_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            provider = self.make_provider(
                workspace,
                "--delay-turn-events",
                timeout=0.05,
                event_timeout=0.5,
            )
            gateway = AgentGateway({"codex": provider})
            gateway.connect("codex")
            session = gateway.create_session("codex", workspace)

            events = list(gateway.send("codex", session, "hello"))

            self.assertEqual(events[-1].kind, "turn.completed")
            gateway.close()

    def test_default_start_command_contains_no_bypass_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = CodexProvider(Path(directory))

            self.assertEqual(provider.start_command[1:], ("app-server", "--stdio"))
            self.assertNotIn("danger-full-access", " ".join(provider.start_command))
            self.assertNotIn("bypass", " ".join(provider.start_command))


if __name__ == "__main__":
    unittest.main()
