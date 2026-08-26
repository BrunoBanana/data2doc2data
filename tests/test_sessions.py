from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.sessions import (
    AuditEntry,
    AuditStore,
    SessionRecord,
    SessionStore,
    SessionStoreError,
)


class SessionPersistenceTests(unittest.TestCase):
    def test_audit_log_is_private_append_only_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "audit.jsonl"
            store = AuditStore(path)
            entry = AuditEntry(
                timestamp=datetime(2026, 8, 16, tzinfo=timezone.utc),
                provider="codex",
                session_id="session-1",
                operation="command",
                summary="curl -H 'Authorization: Bearer private-token' API_KEY=hidden",
                decision="allowed",
                exit_status=0,
                target_paths=("/workspace/report.md",),
            )

            store.append(entry)
            store.append(entry)

            content = path.read_text(encoding="utf-8")
            records = [json.loads(line) for line in content.splitlines()]
            self.assertEqual(len(records), 2)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("private-token", content)
            self.assertNotIn("hidden", content)
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("environment", records[0])

    def test_session_store_round_trip_uses_private_atomic_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "sessions.json"
            store = SessionStore(path)
            record = SessionRecord(
                id="session-1",
                provider="codex",
                provider_session_id="thread-1",
                workspace="/workspace",
                permission_mode="collaborative",
                created_at="2026-08-16T00:00:00+00:00",
                updated_at="2026-08-16T00:00:00+00:00",
            )

            store.upsert(record)

            self.assertEqual(store.get("session-1"), record)
            self.assertEqual(store.list(), (record,))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_corrupt_session_store_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sessions.json"
            path.write_text("not-json", encoding="utf-8")

            with self.assertRaisesRegex(SessionStoreError, "cannot read"):
                SessionStore(path).list()


if __name__ == "__main__":
    unittest.main()
