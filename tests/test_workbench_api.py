import json
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data2doc2data.config import ProfileStore
from data2doc2data.agent_api import BrowserSessions
from data2doc2data.run_events import RunEvent
from data2doc2data.server import create_server
from data2doc2data.workspace import SnapshotRef


class WorkbenchApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.profile_store = ProfileStore(Path(self.temporary_directory.name) / "state" / "config.json")
        self.server = create_server(self.profile_store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.cookie, self.csrf = self.authenticate()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temporary_directory.cleanup()

    def authenticate(self):
        status, payload, headers = self.request("GET", "/api/agents")
        self.assertEqual(status, 200)
        return headers["Set-Cookie"].split(";", 1)[0], payload["csrf_token"]

    def test_task_create_list_update_and_csrf_boundary(self):
        status, payload, _ = self.request(
            "POST",
            "/api/workbench/tasks",
            {"title": "区域增长复盘", "goal": "解释收入下降"},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, payload)
        task = payload["task"]
        self.assertTrue(task["task_id"].startswith("task-"))

        status, listed, _ = self.request("GET", "/api/workbench/tasks", cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual(listed["tasks"], [task])

        status, updated, _ = self.request(
            "PUT",
            f"/api/workbench/tasks/{task['task_id']}",
            {"title": "区域收入复盘", "goal": "解释收入与订单下降"},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["task"]["title"], "区域收入复盘")

        status, error, _ = self.request(
            "POST", "/api/workbench/tasks", {"title": "No CSRF", "goal": "blocked"}, cookie=self.cookie
        )
        self.assertEqual(status, 403)
        self.assertEqual(error["error"], "agent request authorization failed")

    def test_bootstrap_refresh_keeps_the_current_browser_owner(self):
        task = self.create_task()

        status, payload, headers = self.request("GET", "/api/agents", cookie=self.cookie)

        self.assertEqual(status, 200)
        self.assertNotEqual(payload["csrf_token"], self.csrf)
        self.assertEqual(headers["Set-Cookie"].split(";", 1)[0], self.cookie)
        status, listed, _ = self.request("GET", "/api/workbench/tasks", cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual([item["task_id"] for item in listed["tasks"]], [task["task_id"]])

    def test_expired_browser_lease_renews_without_losing_owned_tasks(self):
        now = [100.0]
        self.server.agent_service.browser_sessions = BrowserSessions(
            lifetime_seconds=10,
            clock=lambda: now[0],
        )
        cookie, csrf = self.authenticate()
        status, created, _ = self.request(
            "POST",
            "/api/workbench/tasks",
            {"title": "长期调查", "goal": "跨时段保持工作区"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 201, created)
        now[0] = 111.0

        status, bootstrap, headers = self.request("GET", "/api/agents", cookie=cookie)
        renewed_cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, listed, _ = self.request("GET", "/api/workbench/tasks", cookie=renewed_cookie)

        self.assertEqual(status, 200, listed)
        self.assertEqual(renewed_cookie, cookie)
        self.assertNotEqual(bootstrap["csrf_token"], csrf)
        self.assertEqual([item["task_id"] for item in listed["tasks"]], [created["task"]["task_id"]])

    def test_flagship_cases_are_safe_and_load_as_complete_owned_tasks(self):
        status, catalog, _ = self.request("GET", "/api/workbench/cases", cookie=self.cookie)

        self.assertEqual(status, 200, catalog)
        self.assertEqual(
            [case["id"] for case in catalog["cases"]],
            ["saas-growth-retention", "retail-promotion-fulfillment"],
        )
        self.assertTrue(all(case["synthetic"] for case in catalog["cases"]))
        self.assertNotIn("/Users/", json.dumps(catalog))
        self.assertNotIn("metrics_path", json.dumps(catalog))

        status, unauthorized, _ = self.request(
            "POST",
            "/api/workbench/cases/saas-growth-retention/load",
            {},
            cookie=self.cookie,
        )
        self.assertEqual(status, 403, unauthorized)

        status, loaded, _ = self.request(
            "POST",
            "/api/workbench/cases/saas-growth-retention/load",
            {},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, loaded)
        task = loaded["task"]
        self.assertEqual(task["title"], "增长提速、留存承压")
        self.assertEqual([ref["kind"] for ref in task["snapshot_refs"]].count("dataset"), 1)
        self.assertEqual([ref["kind"] for ref in task["snapshot_refs"]].count("document"), 4)
        self.assertEqual(loaded["dashboard"]["dashboard"]["blocks"][0]["value"], 208)
        self.assertEqual(loaded["dashboard"]["text_dashboard"]["document_count"], 4)
        self.assertGreaterEqual(len(loaded["dashboard"]["text_dashboard"]["claims"]), 3)

        artifact = self.server.workbench_store.get_task_artifact(task["task_id"], "flagship_case")
        self.assertEqual(artifact["case"]["id"], "saas-growth-retention")
        self.assertEqual(len(artifact["rules"]["rules"]), 3)
        self.assertEqual(len(artifact["hypotheses"]["hypotheses"]), 3)
        self.assertNotIn("metrics_path", json.dumps(artifact))

        status, analysis, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {"execute": True, "proposal": {"hypotheses": []}},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, analysis)
        self.assertIn("H1", [node["node_id"] for node in analysis["evidence_graph"]["nodes"]])

        other_cookie, _ = self.authenticate()
        status, hidden, _ = self.request("GET", f"/api/workbench/tasks/{task['task_id']}", cookie=other_cookie)
        self.assertEqual(status, 404, hidden)

    def test_assets_runs_event_replay_and_browser_ownership(self):
        task = self.create_task()
        snapshot = {"kind": "dataset", "snapshot_id": "dataset-1", "sha256": "a" * 64}
        status, attached, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, attached)
        self.assertEqual(attached["task"]["snapshot_refs"], [snapshot])

        status, started, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, started)
        run = started["run"]
        self.assertEqual(run["status"], "running")
        self.assertEqual(run["snapshot_refs"], [snapshot])
        self.server.workbench_store.append_event(
            RunEvent.create(run["run_id"], 2, "data.profiled", "profile", {"row_count": 12})
        )

        status, replay, _ = self.request(
            "GET", f"/api/workbench/runs/{run['run_id']}/events?after=1", cookie=self.cookie
        )
        self.assertEqual(status, 200, replay)
        self.assertEqual([event["sequence"] for event in replay["events"]], [2])

        other_cookie, _ = self.authenticate()
        status, hidden, _ = self.request("GET", f"/api/workbench/tasks/{task['task_id']}", cookie=other_cookie)
        self.assertEqual(status, 404)
        self.assertEqual(hidden["error"], "task not found")

    def test_invalid_payload_identifiers_and_replay_limits_are_rejected(self):
        status, payload, _ = self.request(
            "POST",
            "/api/workbench/tasks",
            {"title": " ", "goal": "Goal"},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 422)
        self.assertIn("title", payload["error"])

        status, payload, _ = self.request("GET", "/api/workbench/tasks/bad%2Fid", cookie=self.cookie)
        self.assertEqual(status, 404)

        task = self.create_task()
        status, started, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        run_id = started["run"]["run_id"]
        status, payload, _ = self.request("GET", f"/api/workbench/runs/{run_id}/events?limit=1001", cookie=self.cookie)
        self.assertEqual(status, 422)
        self.assertIn("limit", payload["error"])

    def test_task_dashboard_and_document_import_use_registered_snapshots(self):
        task = self.create_task()
        dataset = Path(self.temporary_directory.name) / "standard.csv"
        dataset.write_text("date,metric,value\n2026-01-01,收入,10\n2026-02-01,收入,12\n", encoding="utf-8")
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        snapshot = {"kind": "dataset", "snapshot_id": f"dataset-{digest[:24]}", "sha256": digest}
        self.server.workbench_store.register_snapshot(SnapshotRef.from_dict(snapshot), dataset)
        status, _, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200)

        document = Path(self.temporary_directory.name) / "plan.md"
        document.write_text("# 目标\n主张：收入将持续增长\n", encoding="utf-8")
        status, imported, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/documents",
            {"paths": [str(document)]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, imported)
        self.assertEqual(imported["text_dashboard"]["document_count"], 1)

        status, payload, _ = self.request(
            "GET", f"/api/workbench/tasks/{task['task_id']}/dashboard", cookie=self.cookie
        )
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["dashboard"]["blocks"][0]["value"], 2)
        self.assertEqual(payload["text_dashboard"]["claims"][0]["status"], "pending")

        document.write_text("# altered\n", encoding="utf-8")
        status, stale, _ = self.request("GET", f"/api/workbench/tasks/{task['task_id']}/dashboard", cookie=self.cookie)
        self.assertEqual(status, 409)
        self.assertIn("document snapshot content has changed", stale["error"])

    def test_partial_document_import_diagnostics_survive_dashboard_reload(self):
        task = self.create_task()
        document = Path(self.temporary_directory.name) / "plan.md"
        document.write_text("# 目标\n主张：收入将持续增长\n", encoding="utf-8")
        missing = Path(self.temporary_directory.name) / "missing.md"

        status, imported, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/documents",
            {"paths": [str(document), str(missing)]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, imported)
        self.assertEqual(imported["text_dashboard"]["document_count"], 1)
        self.assertEqual(imported["text_dashboard"]["failure_count"], 1)

        status, reloaded, _ = self.request(
            "GET", f"/api/workbench/tasks/{task['task_id']}/dashboard", cookie=self.cookie
        )
        self.assertEqual(status, 200, reloaded)
        self.assertEqual(reloaded["text_dashboard"]["document_count"], 1)
        self.assertEqual(reloaded["text_dashboard"]["failure_count"], 1)

    def test_all_failed_document_import_diagnostics_survive_dashboard_reload(self):
        task = self.create_task()
        missing = Path(self.temporary_directory.name) / "missing.md"

        status, imported, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/documents",
            {"paths": [str(missing)]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, imported)
        self.assertEqual(imported["text_dashboard"]["document_count"], 0)
        self.assertEqual(imported["text_dashboard"]["failure_count"], 1)

        status, reloaded, _ = self.request(
            "GET", f"/api/workbench/tasks/{task['task_id']}/dashboard", cookie=self.cookie
        )
        self.assertEqual(status, 200, reloaded)
        self.assertEqual(reloaded["text_dashboard"]["document_count"], 0)
        self.assertEqual(reloaded["text_dashboard"]["failure_count"], 1)

    def test_executed_run_returns_observable_events_and_evidence_graph(self):
        task = self.create_task()
        dataset = Path(self.temporary_directory.name) / "standard.csv"
        dataset.write_text("date,metric,value\n2026-01-01,收入,10\n2026-02-01,收入,12\n", encoding="utf-8")
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        snapshot = {"kind": "dataset", "snapshot_id": f"dataset-{digest[:24]}", "sha256": digest}
        self.server.workbench_store.register_snapshot(SnapshotRef.from_dict(snapshot), dataset)
        self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )

        status, payload, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {
                "execute": True,
                "proposal": {"hypotheses": [{"hypothesis_id": "hypothesis-price", "text": "价格调整影响收入"}]},
            },
            cookie=self.cookie,
            csrf=self.csrf,
        )

        self.assertEqual(status, 201, payload)
        self.assertEqual(payload["run"]["status"], "completed")
        self.assertEqual(payload["events"][-1]["kind"], "run.completed")
        self.assertIn("hypothesis-price", [node["node_id"] for node in payload["evidence_graph"]["nodes"]])
        run_id = payload["run"]["run_id"]
        status, graph, _ = self.request("GET", f"/api/workbench/runs/{run_id}/graph", cookie=self.cookie)
        self.assertEqual(status, 200)
        self.assertEqual(graph["evidence_graph"]["graph_id"], payload["evidence_graph"]["graph_id"])

        status, history, _ = self.request("GET", f"/api/workbench/tasks/{task['task_id']}/runs", cookie=self.cookie)
        self.assertEqual(status, 200, history)
        self.assertEqual(history["runs"][0]["run_id"], run_id)
        self.assertFalse(history["runs"][0]["stale"])

        status, detail, _ = self.request("GET", f"/api/workbench/runs/{run_id}", cookie=self.cookie)
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["events"][-1]["kind"], "run.completed")
        self.assertEqual(detail["evidence_graph"]["graph_id"], payload["evidence_graph"]["graph_id"])

    def test_streamed_run_returns_202_and_sse_replays_from_a_cursor(self):
        task = self.create_task()
        dataset = Path(self.temporary_directory.name) / "stream.csv"
        dataset.write_text(
            "date,metric,value\n2026-01-01,revenue,10\n2026-02-01,revenue,12\n",
            encoding="utf-8",
        )
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        snapshot = {
            "kind": "dataset",
            "snapshot_id": f"dataset-{digest[:24]}",
            "sha256": digest,
        }
        self.server.workbench_store.register_snapshot(SnapshotRef.from_dict(snapshot), dataset)
        self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )

        status, started, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {"execute": True, "stream": True},
            cookie=self.cookie,
            csrf=self.csrf,
        )

        self.assertEqual(status, 202, started)
        run_id = started["run"]["run_id"]
        request = Request(
            f"{self.base_url}/api/workbench/runs/{run_id}/stream?after=1",
            headers={"Cookie": self.cookie, "Last-Event-ID": "1"},
        )
        with urlopen(request, timeout=4) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.headers["Content-Type"], "text/event-stream; charset=utf-8")
        event_ids = [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]
        self.assertTrue(event_ids)
        self.assertTrue(all(event_id > 1 for event_id in event_ids))
        self.assertEqual(event_ids, sorted(set(event_ids)))
        self.assertIn('"kind":"run.completed"', body)

    def test_failed_run_can_be_retried_idempotently_without_mutating_history(self):
        task = self.create_task()
        dataset = Path(self.temporary_directory.name) / "standard.csv"
        dataset.write_text("date,metric,value\n2026-01-01,收入,10\n2026-02-01,收入,12\n", encoding="utf-8")
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        snapshot = {"kind": "dataset", "snapshot_id": f"dataset-{digest[:24]}", "sha256": digest}
        self.server.workbench_store.register_snapshot(SnapshotRef.from_dict(snapshot), dataset)
        self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        status, first, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {"execute": True},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, first)

        retry_body = {"idempotency_key": "retry-button-0001"}
        status, retried, _ = self.request(
            "POST",
            f"/api/workbench/runs/{first['run']['run_id']}/retry",
            retry_body,
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, retried)
        self.assertNotEqual(retried["run"]["run_id"], first["run"]["run_id"])
        self.assertEqual(retried["retried_from"], first["run"]["run_id"])
        self.assertFalse(retried["replayed"])

        status, repeated, _ = self.request(
            "POST",
            f"/api/workbench/runs/{first['run']['run_id']}/retry",
            retry_body,
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 200, repeated)
        self.assertEqual(repeated["run"]["run_id"], retried["run"]["run_id"])
        self.assertTrue(repeated["replayed"])
        self.assertEqual(len(self.server.workbench_store.list_runs(task["task_id"])), 2)

    def test_task_report_download_is_authenticated_standalone_html(self):
        task = self.create_task()
        dataset = Path(self.temporary_directory.name) / "standard.csv"
        dataset.write_text("date,metric,value\n2026-01-01,收入,10\n2026-02-01,收入,12\n", encoding="utf-8")
        digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
        snapshot = {"kind": "dataset", "snapshot_id": f"dataset-{digest[:24]}", "sha256": digest}
        self.server.workbench_store.register_snapshot(SnapshotRef.from_dict(snapshot), dataset)
        self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/assets",
            {"snapshot_refs": [snapshot]},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {"execute": True},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        status, _, _ = self.request(
            "POST",
            f"/api/workbench/tasks/{task['task_id']}/runs",
            {"execute": True, "proposal": {"hypotheses": "invalid"}},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 422)

        request = Request(
            f"{self.base_url}/api/workbench/tasks/{task['task_id']}/report", headers={"Cookie": self.cookie}
        )
        with urlopen(request, timeout=2) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("attachment; filename=", response.headers["Content-Disposition"])
            self.assertIn("<h2>分析结论</h2>", html)
            self.assertIn('aria-label="证据验证"', html)
        self.assertIn("<svg", html)
        self.assertIn("<td>data_source</td>", html)
        self.assertNotIn("<script", html)

        status, payload, _ = self.request("GET", f"/api/workbench/tasks/{task['task_id']}/report")
        self.assertEqual(status, 403, payload)

    def create_task(self):
        status, payload, _ = self.request(
            "POST",
            "/api/workbench/tasks",
            {"title": "复盘", "goal": "解释变化"},
            cookie=self.cookie,
            csrf=self.csrf,
        )
        self.assertEqual(status, 201, payload)
        return payload["task"]

    def request(self, method, path, payload=None, cookie=None, csrf=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8")), response.headers
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8")), error.headers
            finally:
                error.close()


if __name__ == "__main__":
    unittest.main()
