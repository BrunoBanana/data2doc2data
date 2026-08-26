from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from data2doc2data.permissions import OperationRequest, PermissionBroker


class PermissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name).resolve()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def request(self, **overrides):
        values = {
            "provider": "codex",
            "session_id": "session-1",
            "kind": "command",
            "working_directory": self.workspace,
            "target_paths": (self.workspace / "report.md",),
            "command": "git status",
            "summary": "Inspect repository status",
        }
        values.update(overrides)
        return OperationRequest(**values)

    def test_collaborative_mode_blocks_command_until_approved(self):
        broker = PermissionBroker(mode="collaborative", roots=(self.workspace,))

        decision = broker.evaluate(self.request())

        self.assertEqual(decision.status, "pending")

    def test_collaborative_approval_is_bound_to_one_request(self):
        broker = PermissionBroker(mode="collaborative", roots=(self.workspace,))
        request = self.request()
        broker.approve(request)

        replacement = broker.evaluate(self.request())
        approved = broker.evaluate(request)
        replay = broker.evaluate(request)

        self.assertEqual(approved.status, "allowed")
        self.assertEqual(replay.status, "pending")
        self.assertEqual(replacement.status, "pending")

    def test_read_only_mode_allows_reads_but_rejects_writes(self):
        broker = PermissionBroker(mode="read_only", roots=(self.workspace,))

        read = broker.evaluate(self.request(kind="read", command=None))
        write = broker.evaluate(self.request(kind="write", command=None))

        self.assertEqual(read.status, "allowed")
        self.assertEqual(write.status, "rejected")

    def test_target_outside_workspace_is_rejected_even_after_approval(self):
        outside = self.workspace.parent / "outside.txt"
        broker = PermissionBroker(mode="trusted_session", roots=(self.workspace,))
        request = self.request(kind="write", command=None, target_paths=(outside,))

        approval = broker.approve(request)
        decision = broker.evaluate(request)

        self.assertEqual(approval.status, "rejected")
        self.assertEqual(decision.status, "rejected")

    def test_trusted_grant_is_scoped_to_provider_session_kind_prefix_and_root(self):
        broker = PermissionBroker(mode="trusted_session", roots=(self.workspace,))
        broker.approve(self.request(), command_prefix="git status")

        matching = broker.evaluate(self.request(command="git status --short"))
        other_provider = broker.evaluate(self.request(provider="workbuddy"))
        other_session = broker.evaluate(self.request(session_id="session-2"))
        other_kind = broker.evaluate(self.request(kind="write", command=None))
        other_command = broker.evaluate(self.request(command="git commit -m test"))

        self.assertEqual(matching.status, "allowed")
        for decision in (other_provider, other_session, other_kind, other_command):
            self.assertEqual(decision.status, "pending")

    def test_expired_trusted_grant_returns_to_pending(self):
        now = datetime(2026, 8, 16, tzinfo=timezone.utc)
        broker = PermissionBroker(
            mode="trusted_session",
            roots=(self.workspace,),
            clock=lambda: now,
        )
        broker.approve(self.request(), ttl_seconds=30)
        broker.clock = lambda: now + timedelta(seconds=31)

        self.assertEqual(broker.evaluate(self.request()).status, "pending")

    def test_command_grant_prefix_must_match_the_approved_request(self):
        broker = PermissionBroker(mode="trusted_session", roots=(self.workspace,))

        with self.assertRaisesRegex(ValueError, "prefix"):
            broker.approve(self.request(command="git status"), command_prefix="rm")


if __name__ == "__main__":
    unittest.main()
