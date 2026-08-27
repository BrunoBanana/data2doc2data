from pathlib import Path
from queue import Queue
import sys
import tempfile
import unittest
from unittest.mock import Mock

from data2doc2data.agents.base import AgentEvent, AgentSession
from data2doc2data.agents.codex import CodexProvider, _nested_text, _resolve_codex_executable
from data2doc2data.agents.gateway import AgentGateway, ProviderTimeout
from data2doc2data.analysis import analyze
from data2doc2data.config import Profile


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "codex_app_server"
FAKE_SERVER = FIXTURE_ROOT / "fake_app_server.py"


class CodexAdapterTests(unittest.TestCase):
    def make_provider(self, workspace, *server_args, timeout=2.0, event_timeout=None, turn_timeout=90.0):
        return CodexProvider(
            workspace=workspace,
            executable=sys.executable,
            version_command=(sys.executable, str(FAKE_SERVER), "--version"),
            app_server_command=(sys.executable, "-u", str(FAKE_SERVER), *server_args),
            request_timeout=timeout,
            event_timeout=event_timeout,
            turn_timeout=turn_timeout,
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

    def test_next_turn_reconnects_and_resumes_after_app_server_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            marker = workspace / "crash-once.marker"
            provider = self.make_provider(workspace, "--crash-once", str(marker))
            provider.connect()
            session_id = provider.create_session(workspace)
            from data2doc2data.agents.base import AgentSession

            session = AgentSession("local-1", "codex", session_id, workspace.resolve())
            first = list(provider.stream_turn(session, "first"))
            second = list(provider.stream_turn(session, "second"))

            self.assertEqual(first[-1].kind, "provider.error")
            self.assertEqual(second[-1].kind, "turn.completed")
            self.assertEqual(
                [event.payload.get("state") for event in second[:2]],
                ["reconnecting", "connected"],
            )
            self.assertEqual(second[2].payload["text"], "hello from codex")
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

    def test_total_turn_timeout_interrupts_even_when_no_events_arrive(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            provider = self.make_provider(
                workspace,
                "--delay-turn-events",
                timeout=0.5,
                event_timeout=1.0,
                turn_timeout=0.02,
            )
            gateway = AgentGateway({"codex": provider})
            gateway.connect("codex")
            session = gateway.create_session("codex", workspace)

            with self.assertRaisesRegex(ProviderTimeout, "timed out"):
                list(gateway.send("codex", session, "hello"))

            gateway.close()

    def test_default_start_command_contains_no_bypass_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = CodexProvider(Path(directory))

            self.assertEqual(provider.start_command[1:], ("app-server", "--stdio"))
            self.assertNotIn("danger-full-access", " ".join(provider.start_command))
            self.assertNotIn("bypass", " ".join(provider.start_command))

    def test_runtime_resolution_prefers_a_bundled_codex_with_its_required_host(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path_only = root / "path" / "codex"
            bundled = root / "bundle" / "codex"
            path_only.parent.mkdir()
            bundled.parent.mkdir()
            path_only.write_text("", encoding="utf-8")
            bundled.write_text("", encoding="utf-8")
            bundled.with_name("codex-code-mode-host").write_text("", encoding="utf-8")

            selected = _resolve_codex_executable(
                "codex",
                resolved_path=path_only,
                bundled_candidates=(bundled,),
            )

        self.assertEqual(selected, str(bundled))

    def test_planning_turn_uses_bounded_low_reasoning_effort(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            provider = CodexProvider(workspace)
            session = AgentSession("local-1", "codex", "thread-1", workspace)
            provider._event_queues["thread-1"] = Queue()
            provider._event_queues["thread-1"].put(AgentEvent("turn.completed", {"turn_id": "turn-1"}))
            provider._validate_session = Mock()
            provider._request = Mock(return_value={"turn": {"id": "turn-1"}})

            events = list(provider.stream_turn(session, "choose a tool"))

        params = provider._request.call_args.args[1]
        self.assertEqual(params["effort"], "low")
        self.assertEqual(events[-1].kind, "turn.completed")

    def test_planning_session_is_ephemeral_and_disables_user_mcp_servers(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            provider = CodexProvider(workspace)
            provider._require_connected = Mock()
            provider._request = Mock(return_value={"thread": {"id": "thread-isolated"}})

            session_id = provider.create_session(workspace)

        params = provider._request.call_args.args[1]
        self.assertEqual(session_id, "thread-isolated")
        self.assertTrue(params["ephemeral"])
        self.assertEqual(params["config"], {"mcp_servers": {}})

    def test_failed_turn_surfaces_the_provider_reason_and_code(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = CodexProvider(Path(directory))

            events = provider._notification_events(
                "turn/completed",
                {
                    "turn": {
                        "id": "turn-usage-limit",
                        "status": "failed",
                        "error": {
                            "message": "You've hit your usage limit.",
                            "codexErrorInfo": "usageLimitExceeded",
                        },
                    }
                },
            )

            self.assertEqual(events[0].kind, "turn.error")
            self.assertEqual(events[0].payload["message"], "You've hit your usage limit.")
            self.assertEqual(events[0].payload["code"], "usageLimitExceeded")


class CodexProtocolHelpersTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.provider = CodexProvider(Path(self._tmp.name))

    def test_nested_text_walks_mapping_paths(self):
        self.assertEqual(_nested_text({"thread": {"id": "t-1"}}, "thread", "id"), "t-1")
        self.assertIsNone(_nested_text({"thread": {}}, "thread", "id"))
        self.assertIsNone(_nested_text({"thread": "not-a-map"}, "thread", "id"))
        self.assertIsNone(_nested_text(None, "thread", "id"))

    def test_file_patch_delta_maps_to_file_diff_events(self):
        events = self.provider._notification_events(
            "item/fileChange/patchUpdated",
            {"changes": [{"path": "a.txt", "diff": "-x\n+y"}]},
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].kind, "file.diff")
        self.assertEqual(events[0].payload["path"], "a.txt")
        self.assertEqual(events[0].payload["diff"], "-x\n+y")

    def test_completed_agent_message_maps_to_public_message_delta(self):
        events = self.provider._notification_events(
            "item/completed",
            {
                "threadId": "thread-1",
                "turnId": "turn-1",
                "completedAtMs": 1,
                "item": {
                    "id": "message-1",
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": '{"action":"finish"}',
                },
            },
        )

        self.assertEqual(events, [AgentEvent("message.delta", {"text": '{"action":"finish"}'})])

    def test_completed_commentary_and_delta_duplicates_are_not_public_decisions(self):
        commentary = self.provider._notification_events(
            "item/completed",
            {
                "item": {
                    "id": "message-commentary",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "working",
                }
            },
        )
        delta = self.provider._notification_events(
            "item/agentMessage/delta",
            {"itemId": "message-delta", "delta": "public"},
        )
        duplicate = self.provider._notification_events(
            "item/completed",
            {"item": {"id": "message-delta", "type": "agentMessage", "text": "public"}},
        )

        self.assertEqual(commentary, [])
        self.assertEqual(delta, [AgentEvent("message.delta", {"text": "public"})])
        self.assertEqual(duplicate, [])

    def test_interrupted_turn_maps_to_cancelled(self):
        events = self.provider._notification_events(
            "turn/completed",
            {"turn": {"id": "turn-1", "status": "interrupted"}},
        )

        self.assertEqual(events[0].kind, "turn.cancelled")
        self.assertEqual(events[0].payload["turn_id"], "turn-1")

    def test_completed_turn_maps_to_completed(self):
        events = self.provider._notification_events("turn/completed", {"turn": {"id": "turn-1", "status": "completed"}})

        self.assertEqual(events[0].kind, "turn.completed")

    def test_malformed_file_changes_are_rejected(self):
        from data2doc2data.agents.gateway import InvalidProviderPayload

        with self.assertRaises(InvalidProviderPayload):
            self.provider._notification_events("item/fileChange/patchUpdated", {"changes": "nope"})


if __name__ == "__main__":
    unittest.main()
