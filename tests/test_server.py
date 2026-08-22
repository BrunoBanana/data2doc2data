import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data2doc2data.config import ProfileStore
from data2doc2data.server import create_server


class LocalServerTests(unittest.TestCase):
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

    def test_profile_api_reports_unconfigured_state(self):
        status, payload = request_json(self.base_url, "GET", "/api/profile")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"configured": False, "profile": None})

    def test_workbench_routes_require_a_browser_session(self):
        status, payload = request_json(self.base_url, "GET", "/api/workbench/tasks")

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "agent request authorization failed")

    def test_demo_scenario_api_returns_ordered_metadata_without_paths(self):
        status, payload = request_json(self.base_url, "GET", "/api/demo-scenarios")

        self.assertEqual(status, 200)
        self.assertEqual(payload["default"], "growth-quality-alert")
        self.assertEqual(
            [scenario["id"] for scenario in payload["scenarios"]],
            ["growth-quality-alert", "strategy-data-conflict", "insufficient-evidence"],
        )
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("metrics.csv", encoded)
        self.assertNotIn("strategy.md", encoded)
        self.assertNotIn(str(Path(__file__).resolve().parent), encoded)

    def test_source_profile_api_returns_safe_default_demo_counts(self):
        status, payload = request_json(self.base_url, "GET", "/api/source-profile")

        self.assertEqual(status, 200)
        self.assertEqual(payload["record_count"], 12)
        self.assertEqual(payload["metrics"], ["activation_rate", "retention_rate"])
        self.assertEqual(len(payload["observation_dates"]), 6)
        self.assertEqual(payload["document_count"], 1)
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("metrics.csv", encoded)
        self.assertNotIn("strategy.md", encoded)
        self.assertNotIn("0.66", encoded)

    def test_profile_api_reports_a_corrupt_local_profile(self):
        self.store.path.write_text("not JSON", encoding="utf-8")

        status, payload = request_json(self.base_url, "GET", "/api/profile")

        self.assertEqual(status, 422)
        self.assertIn("cannot read profile", payload["error"])

    def test_server_rejects_non_loopback_host(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            create_server(self.store, host="0.0.0.0", port=0)

    def test_server_rejects_an_untrusted_host_header(self):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("GET", "/api/profile", headers={"Host": "example.test"})
        response = connection.getresponse()
        try:
            self.assertEqual(response.status, 400)
        finally:
            response.read()
            connection.close()

    def test_static_page_has_local_security_headers(self):
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            self.assertEqual(response.headers["Content-Security-Policy"], "default-src 'self'; base-uri 'none'; form-action 'self'")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

    def test_server_serves_a_local_favicon(self):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("GET", "/favicon.svg", headers={"Host": f"127.0.0.1:{self.server.server_port}"})
        response = connection.getresponse()
        try:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
            self.assertIn(b"<svg", response.read())
        finally:
            connection.close()

    def test_profile_api_rejects_a_missing_local_path(self):
        status, payload = request_json(
            self.base_url,
            "PUT",
            "/api/profile",
            {"mode": "local", "data_path": "/missing.csv", "knowledge_path": "/missing"},
        )

        self.assertEqual(status, 422)
        self.assertIn("CSV file", payload["error"])

    def test_analysis_api_returns_demo_evidence(self):
        status, payload = request_json(
            self.base_url,
            "POST",
            "/api/analyze",
            {"question": "Why did retention fall?"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["signal"]["metric"], "retention_rate")
        self.assertEqual(payload["validation"]["status"], "supported")
        self.assertEqual(payload["verification"]["status"], "confirmed")
        self.assertEqual(payload["verification"]["metric"], "activation_rate")
        self.assertEqual(len(payload["evidence"]), 3)
        self.assertIn("验证指标：激活率", payload["evidence"][2])

    def test_analysis_api_accepts_metric_override(self):
        status, payload = request_json(
            self.base_url,
            "POST",
            "/api/analyze",
            {"question": "What changed?", "metric_override": "retention_rate"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["signal"]["metric"], "retention_rate")

    def test_saved_demo_scenario_controls_subsequent_analysis(self):
        save_status, saved = request_json(
            self.base_url,
            "PUT",
            "/api/profile",
            {"mode": "demo", "demo_scenario": "strategy-data-conflict"},
        )
        analysis_status, result = request_json(
            self.base_url,
            "POST",
            "/api/analyze",
            {"question": "留存变化符合策略预期吗？"},
        )

        self.assertEqual(save_status, 200)
        self.assertEqual(saved["profile"]["demo_scenario"], "strategy-data-conflict")
        self.assertEqual(analysis_status, 200)
        self.assertEqual(result["validation"]["status"], "contradicted")

    def test_profile_api_rejects_an_invalid_demo_scenario(self):
        status, payload = request_json(
            self.base_url,
            "PUT",
            "/api/profile",
            {"mode": "demo", "demo_scenario": "../../private"},
        )

        self.assertEqual(status, 422)
        self.assertIn("scenario", payload["error"])


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


if __name__ == "__main__":
    unittest.main()
