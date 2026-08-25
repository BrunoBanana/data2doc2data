import json
import re
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

    def test_local_presentation_is_served_from_one_fixed_workspace_file(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            presentation = workspace / "docs" / "pitch" / "data2doc2data-defense.html"
            detailed_presentation = workspace / "docs" / "pitch" / "data2doc2data-defense-detailed.html"
            presentation.parent.mkdir(parents=True)
            presentation.write_text("<!doctype html><title>Private local presentation</title>", encoding="utf-8")
            detailed_presentation.write_text(
                "<!doctype html><title>Private detailed presentation</title>", encoding="utf-8"
            )
            server = create_server(self.store, port=0, agent_workspace=workspace)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/__presentation", timeout=2) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("Private local presentation", response.read().decode("utf-8"))
                    self.assertEqual(
                        response.headers["Content-Security-Policy"],
                        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                        "img-src data:; frame-src 'self'; base-uri 'none'; form-action 'none'",
                    )
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                with urlopen(
                    f"http://127.0.0.1:{server.server_port}/__presentation?variant=detailed&live_demo=1",
                    timeout=2,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("Private detailed presentation", response.read().decode("utf-8"))
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                with self.assertRaises(HTTPError) as error:
                    urlopen(
                        f"http://127.0.0.1:{server.server_port}/__presentation?variant=unknown",
                        timeout=2,
                    )
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_local_presentation_does_not_follow_external_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            external = Path(directory) / "outside.html"
            external.write_text("private outside file", encoding="utf-8")
            presentation = workspace / "docs" / "pitch" / "data2doc2data-defense.html"
            presentation.parent.mkdir(parents=True)
            presentation.symlink_to(external)
            server = create_server(self.store, port=0, agent_workspace=workspace)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as error:
                    urlopen(f"http://127.0.0.1:{server.server_port}/__presentation", timeout=2)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_presentation_report_requires_an_authorized_local_browser_session(self):
        status, payload = request_json(self.base_url, "GET", "/__presentation/report")

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "agent request authorization failed")

    def test_presentation_report_serves_one_fixed_private_report_to_its_local_session(self):
        reports = self.store.path.parent / "reports"
        reports.mkdir()
        report = reports / "workbuddy-live-retail-review.html"
        report.write_text("<!doctype html><title>Private verified report</title>", encoding="utf-8")
        with urlopen(f"{self.base_url}/api/agents", timeout=2) as session:
            cookie = session.headers["Set-Cookie"].split(";", maxsplit=1)[0]

        request = Request(f"{self.base_url}/__presentation/report", headers={"Cookie": cookie})
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Private verified report", response.read().decode("utf-8"))
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(
                response.headers["Content-Security-Policy"],
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "base-uri 'none'; form-action 'none'",
            )

    def test_presentation_report_rejects_symlinks_even_if_a_default_report_exists(self):
        reports = self.store.path.parent / "reports"
        reports.mkdir()
        outside = self.store.path.parent / "outside.html"
        outside.write_text("unapproved local file", encoding="utf-8")
        (reports / "workbuddy-live-retail-review.html").symlink_to(outside)
        with urlopen(f"{self.base_url}/api/agents", timeout=2) as session:
            cookie = session.headers["Set-Cookie"].split(";", maxsplit=1)[0]

        request = Request(f"{self.base_url}/__presentation/report", headers={"Cookie": cookie})
        with self.assertRaises(HTTPError) as error:
            urlopen(request, timeout=2)
        self.assertEqual(error.exception.code, 404)
        error.exception.close()

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

    def test_server_serves_react_shell_hashed_assets_and_spa_fallback(self):
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            html = response.read().decode("utf-8")
        script_path = re.search(r'src="(/assets/[^"]+\.js)"', html).group(1)

        with urlopen(f"{self.base_url}{script_path}", timeout=2) as response:
            self.assertEqual(response.headers["Content-Type"], "text/javascript; charset=utf-8")
            self.assertGreater(len(response.read()), 1000)
        with urlopen(f"{self.base_url}/tasks/task-1", timeout=2) as response:
            self.assertIn('id="root"', response.read().decode("utf-8"))

        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.request("GET", "/assets/../index.html", headers={"Host": f"127.0.0.1:{self.server.server_port}"})
        response = connection.getresponse()
        try:
            self.assertEqual(response.status, 404)
        finally:
            response.read()
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
