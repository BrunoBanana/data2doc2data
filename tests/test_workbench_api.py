import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data2doc2data.config import ProfileStore
from data2doc2data.run_events import RunEvent
from data2doc2data.server import create_server


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
        status, payload, _ = self.request(
            "GET", f"/api/workbench/runs/{run_id}/events?limit=1001", cookie=self.cookie
        )
        self.assertEqual(status, 422)
        self.assertIn("limit", payload["error"])

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
