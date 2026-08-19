"""End-to-end HTTP coverage for the ingestion endpoints."""

import base64
import json
import threading
import unittest
from pathlib import Path
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data2doc2data.config import ProfileStore
from data2doc2data.server import create_server


def request_json(base_url, method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode("utf-8"))
        finally:
            error.close()


class IngestionHttpTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.temporary_directory.name) / "config.json")
        self.server = create_server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temporary_directory.cleanup()

    def _upload_csv(self):
        content = base64.b64encode(
            b"date,metric,value\n2026-01-05,retention_rate,0.66\n2026-01-12,retention_rate,0.65\n"
        ).decode("ascii")
        status, payload = request_json(
            self.base_url, "POST", "/api/ingest/upload",
            {"filename": "metrics.csv", "content": content},
        )
        self.assertEqual(status, 200)
        return payload["path"]

    def test_upload_preview_apply_pipeline(self):
        path = self._upload_csv()

        status, preview = request_json(
            self.base_url, "POST", "/api/ingest/preview", {"path": path}
        )
        self.assertEqual(status, 200)
        self.assertEqual(preview["preview"]["fields"], ["date", "metric", "value"])
        self.assertIsNotNone(preview["suggestion"])

        status, applied = request_json(
            self.base_url, "POST", "/api/ingest/apply",
            {
                "path": path,
                "plan": {
                    "format": "csv",
                    "date_field": "date",
                    "metric_field": "metric",
                    "value_field": "value",
                },
                "mode": "local",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(applied["result"]["row_count"], 2)
        self.assertEqual(applied["profile"]["mode"], "local")
        self.assertTrue(Path(applied["profile"]["data_path"]).is_file())

        saved = self.store.load()
        self.assertEqual(saved.data_path, applied["profile"]["data_path"])

    def test_apply_rejects_unparseable_source(self):
        content = base64.b64encode(b"date,metric,value\nbad,also,3\n").decode("ascii")
        status, payload = request_json(
            self.base_url, "POST", "/api/ingest/upload",
            {"filename": "bad.csv", "content": content},
        )
        path = payload["path"]
        status, applied = request_json(
            self.base_url, "POST", "/api/ingest/apply",
            {
                "path": path,
                "plan": {
                    "format": "csv",
                    "date_field": "date",
                    "metric_field": "metric",
                    "value_field": "value",
                },
            },
        )
        self.assertEqual(status, 422)
        self.assertIn("无法转换", applied["error"])

    def test_preview_rejects_missing_file(self):
        status, payload = request_json(
            self.base_url, "POST", "/api/ingest/preview", {"path": "/no/such/file.csv"}
        )
        self.assertEqual(status, 422)
        self.assertIn("文件不存在", payload["error"])


if __name__ == "__main__":
    unittest.main()
