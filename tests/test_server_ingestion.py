"""Server-side ingestion orchestration: upload, preview, apply, API snapshot."""

import base64
import json
import tempfile
import unittest
from pathlib import Path

from data2doc2data.agents.base import AgentEvent, AgentSession, ProviderStatus
from data2doc2data.config import Profile, ProfileStore
from data2doc2data.server import (
    ingest_api_snapshot,
    ingest_apply,
    ingest_preview,
    ingest_propose,
    ingest_upload,
)


def _make_store() -> ProfileStore:
    directory = Path(tempfile.mkdtemp())
    return ProfileStore(directory / "config.json")


def _csv_source() -> Path:
    path = Path(tempfile.mkdtemp()) / "metrics.csv"
    path.write_text(
        "date,metric,value\n2026-01-05,retention_rate,0.66\n2026-01-12,retention_rate,0.65\n",
        encoding="utf-8",
    )
    return path


class UploadTests(unittest.TestCase):
    def test_upload_stores_file_and_returns_path(self):
        store = _make_store()
        content = base64.b64encode(b"date,metric,value\n2026-01-05,a,1\n").decode("ascii")
        result = ingest_upload("report.CSV", content, store)
        saved = Path(result["path"])
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), b"date,metric,value\n2026-01-05,a,1\n")
        self.assertEqual(result["filename"], "report.CSV")

    def test_upload_sanitizes_path_traversal(self):
        store = _make_store()
        content = base64.b64encode(b"x").decode("ascii")
        result = ingest_upload("../../evil.csv", content, store)
        saved = Path(result["path"])
        self.assertEqual(saved.name, "evil.csv")
        self.assertNotIn("..", str(saved))

    def test_upload_rejects_non_base64(self):
        store = _make_store()
        with self.assertRaises(ValueError):
            ingest_upload("a.csv", "not-base64!!", store)

    def test_upload_rejects_oversized(self):
        store = _make_store()
        big = base64.b64encode(b"x" * (6 * 1024 * 1024)).decode("ascii")
        with self.assertRaises(ValueError):
            ingest_upload("big.csv", big, store)


class PreviewTests(unittest.TestCase):
    def test_preview_returns_structure_and_suggestion(self):
        path = _csv_source()
        result = ingest_preview(str(path))
        preview = result["preview"]
        self.assertEqual(preview["fields"], ["date", "metric", "value"])
        self.assertEqual(preview["row_count"], 2)
        self.assertIsNotNone(result["suggestion"])
        self.assertEqual(result["suggestion"]["date_field"], "date")

    def test_preview_rejects_missing_path(self):
        with self.assertRaises(ValueError):
            ingest_preview("")


class ApplyTests(unittest.TestCase):
    def test_apply_produces_standard_csv_and_updates_profile(self):
        store = _make_store()
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(str(source), plan, store, "local")
        standard = Path(result["profile"]["data_path"])
        self.assertTrue(standard.is_file())
        self.assertEqual(standard.read_text(encoding="utf-8").splitlines()[0], "date,metric,value")
        self.assertEqual(result["result"]["row_count"], 2)
        saved = store.load()
        self.assertEqual(saved.mode, "local")
        self.assertEqual(saved.data_path, str(standard))

    def test_apply_preserves_knowledge_path(self):
        store = _make_store()
        store.save(Profile(mode="local", data_path="", knowledge_path="/tmp/docs", demo_scenario="demo"))
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(str(source), plan, store, "api")
        self.assertEqual(result["profile"]["knowledge_path"], "/tmp/docs")
        self.assertEqual(result["profile"]["mode"], "api")

    def test_apply_rejects_bad_plan(self):
        store = _make_store()
        with self.assertRaises(ValueError):
            ingest_apply(str(_csv_source()), {}, store, "local")

    def test_apply_captures_knowledge_path_and_config(self):
        store = _make_store()
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(
            str(source),
            plan,
            store,
            "api",
            knowledge_path="/tmp/my-docs",
            api_config={"url": "https://api.example.com/metrics", "headers": None},
        )
        self.assertEqual(result["profile"]["knowledge_path"], "/tmp/my-docs")
        self.assertEqual(result["profile"]["mode"], "api")
        self.assertEqual(
            result["profile"]["api"],
            {"url": "https://api.example.com/metrics", "headers": None},
        )
        self.assertEqual(result["profile"]["ingestion"]["source_path"], str(source))
        self.assertEqual(result["profile"]["ingestion"]["plan"]["format"], "csv")
        self.assertFalse(result["needs_knowledge_path"])

    def test_apply_flags_missing_knowledge_path(self):
        store = _make_store()
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(str(source), plan, store, "local")
        self.assertTrue(result["needs_knowledge_path"])

    def test_apply_warns_on_missing_knowledge_dir(self):
        store = _make_store()
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(
            str(source), plan, store, "local", knowledge_path="/no/such/dir/xyz"
        )
        self.assertEqual(
            result["knowledge_warning"],
            "文档目录不存在，确定性结论可能缺少证据来源。",
        )
        self.assertFalse(result["needs_knowledge_path"])

    def test_apply_no_warning_on_valid_knowledge_dir(self):
        store = _make_store()
        docs = Path(tempfile.mkdtemp()) / "notes"
        docs.mkdir()
        (docs / "decisions.md").write_text("# notes", encoding="utf-8")
        source = _csv_source()
        plan = {
            "format": "csv",
            "date_field": "date",
            "metric_field": "metric",
            "value_field": "value",
        }
        result = ingest_apply(
            str(source), plan, store, "local", knowledge_path=str(docs)
        )
        self.assertIsNone(result["knowledge_warning"])


class _FakeGateway:
    """Minimal AgentGateway stand-in that returns a fixed mapping proposal."""

    def __init__(self, proposal: str, ready: bool = True) -> None:
        self.provider_names = ("codex",)
        self._proposal = proposal
        self._ready = ready

    def detect(self, _name):
        return ProviderStatus(available=self._ready, connected=self._ready)

    def connect(self, _name):
        return ProviderStatus(available=True, connected=True)

    def create_session(self, _name, workspace):
        return AgentSession(
            id="sess-1",
            provider="codex",
            provider_session_id="prov-1",
            workspace=workspace,
        )

    def send(self, _name, _session, _message):
        yield AgentEvent("message.delta", {"text": self._proposal})


class ProposeTests(unittest.TestCase):
    def _source(self) -> Path:
        return _csv_source()

    def test_propose_falls_back_without_gateway(self):
        source = self._source()
        result = ingest_propose(str(source), None, Path("/tmp"))
        self.assertFalse(result["agent_used"])
        self.assertIsNone(result["agent_plan"])
        self.assertIsNotNone(result["suggestion"])
        self.assertIn("没有可用的本地助手", result["reason"])

    def test_propose_uses_agent_plan(self):
        proposal = (
            '{"format":"csv","date_field":"date","metric_field":"metric",'
            '"value_field":"value"}'
        )
        source = self._source()
        gateway = _FakeGateway(proposal)
        result = ingest_propose(str(source), gateway, Path("/tmp"))
        self.assertTrue(result["agent_used"])
        self.assertEqual(result["agent_plan"]["date_field"], "date")
        self.assertIsNone(result["reason"])

    def test_propose_falls_back_when_agent_unavailable(self):
        source = self._source()
        gateway = _FakeGateway("", ready=False)
        result = ingest_propose(str(source), gateway, Path("/tmp"))
        self.assertFalse(result["agent_used"])
        self.assertIsNotNone(result["suggestion"])


class ApiSnapshotTests(unittest.TestCase):
    def test_api_snapshot_rejects_non_https(self):
        store = _make_store()
        with self.assertRaises(Exception):
            ingest_api_snapshot("http://example.com/x", store)

    def test_api_snapshot_fetches_and_previews(self):
        store = _make_store()
        payload = json.dumps(
            [{"date": "2026-01-05", "metric": "m", "value": 1}]
        ).encode("utf-8")

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self, _n=-1):
                return payload

            @property
            def headers(self):
                return type("H", (), {"get_content_type": lambda self: "application/json"})()

        class _FakeOpener:
            def open(self, _request, timeout=30):
                return _FakeResponse()

        import data2doc2data.ingestion as ingestion_module

        original = ingestion_module.build_opener
        ingestion_module.build_opener = lambda *_a, **_k: _FakeOpener()
        try:
            result = ingest_api_snapshot("https://example.com/metrics", store)
        finally:
            ingestion_module.build_opener = original

        self.assertIn("snapshot", result)
        self.assertTrue(Path(result["snapshot"]["path"]).is_file())
        self.assertEqual(result["preview"]["fields"], ["date", "metric", "value"])
        self.assertIsNotNone(result["suggestion"])


if __name__ == "__main__":
    unittest.main()
