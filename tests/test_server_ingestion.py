"""Server-side ingestion orchestration: upload, preview, apply, API snapshot."""

import base64
import json
import tempfile
import unittest
from pathlib import Path

from data2doc2data.config import Profile, ProfileStore
from data2doc2data.server import (
    ingest_api_snapshot,
    ingest_apply,
    ingest_preview,
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
