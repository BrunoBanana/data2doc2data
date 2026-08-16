import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data2doc2data.agents.base import AgentEvent, ProviderStatus
from data2doc2data.agents.gateway import AgentGateway
from data2doc2data.config import ProfileStore
from data2doc2data.server import MAX_REQUEST_BYTES, create_server


class FakeWebProvider:
    name = "fake"

    def __init__(self, available=True, detail=None):
        self.available = available
        self.detail = detail
        self.connected = False
        self.approval = None
        self.interrupted = None
        self.approval_expires_at = None

    def detect(self):
        return ProviderStatus(self.available, self.connected, version="1.2.3", detail=self.detail)

    def connect(self):
        self.connected = True

    def create_session(self, workspace, resume_id=None):
        return resume_id or "provider-session"

    def stream_turn(self, session, message):
        yield AgentEvent("message.delta", {"text": f"reply: {message}"})
        approval_payload = {
            "request_id": "approval-1",
            "operation": "command",
            "command": "python -m unittest",
            "working_directory": str(session.workspace),
            "target_paths": [],
        }
        if self.approval_expires_at is not None:
            approval_payload["expires_at"] = self.approval_expires_at
        yield AgentEvent(
            "approval.request",
            approval_payload,
        )
        yield AgentEvent("turn.completed", {"turn_id": "turn-1", "reason": "done"})

    def decide_approval(self, session, approval_id, approved):
        self.approval = (session.id, approval_id, approved)

    def interrupt(self, session):
        self.interrupted = session.id

    def close(self):
        return None


class AgentServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name)
        self.store = ProfileStore(self.workspace / "config.json")
        self.provider = FakeWebProvider()
        self.gateway = AgentGateway({"fake": self.provider})
        self.server = create_server(
            self.store,
            port=0,
            gateway=self.gateway,
            agent_workspace=self.workspace,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.temporary_directory.cleanup()

    def authenticate(self):
        status, payload, headers = self.request("GET", "/api/agents")
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        return cookie, payload["csrf_token"], payload

    def create_session(self, mode="collaborative"):
        cookie, csrf, _ = self.authenticate()
        status, payload, _ = self.request(
            "POST",
            "/api/agent-sessions",
            {"provider": "fake", "permission_mode": mode},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 201, payload)
        self.assertNotIn("provider_session_id", payload["session"])
        return cookie, csrf, payload["session"]

    def test_agents_issue_a_short_lived_strict_browser_session(self):
        cookie, csrf, payload = self.authenticate()

        self.assertTrue(cookie.startswith("d2d2d_session="))
        self.assertGreaterEqual(len(csrf), 32)
        self.assertEqual(payload["agents"][0]["name"], "fake")
        self.assertTrue(payload["agents"][0]["available"])

        _, _, headers = self.request("GET", "/api/agents")
        set_cookie = headers["Set-Cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Strict", set_cookie)
        self.assertIn("Max-Age=600", set_cookie)

    def test_mutating_agent_routes_require_cookie_and_csrf(self):
        cookie, csrf, _ = self.authenticate()

        for supplied_cookie, supplied_csrf in ((None, None), (cookie, None), (cookie, "wrong")):
            with self.subTest(cookie=bool(supplied_cookie), csrf=supplied_csrf):
                status, payload, _ = self.request(
                    "POST",
                    "/api/agent-sessions",
                    {"provider": "fake", "permission_mode": "collaborative"},
                    cookie=supplied_cookie,
                    csrf=supplied_csrf,
                )
                self.assertEqual(status, 403)
                self.assertEqual(payload["error"], "agent request authorization failed")

    def test_session_message_stream_approval_and_interrupt(self):
        cookie, csrf, session = self.create_session()
        session_id = session["id"]

        status, payload, _ = self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/messages",
            {"message": "hello"},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 202, payload)

        status, events, _ = self.request(
            "GET",
            f"/api/agent-sessions/{session_id}/events",
            cookie=cookie,
            raw=True,
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [event["kind"] for event in events],
            ["message.delta", "approval.request", "turn.completed"],
        )
        approval = events[1]["payload"]
        self.assertEqual(approval["command"], "python -m unittest")
        self.assertEqual(approval["working_directory"], str(self.workspace.resolve()))

        status, _, _ = self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/approvals/approval-1",
            {"approved": True},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 200)
        self.assertEqual(self.provider.approval, (session_id, "approval-1", True))

        status, _, _ = self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/interrupt",
            {},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 202)
        self.assertEqual(self.provider.interrupted, session_id)

    def test_read_only_session_cannot_approve_a_command(self):
        cookie, csrf, session = self.create_session(mode="read_only")
        session_id = session["id"]
        self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/messages",
            {"message": "hello"},
            cookie=cookie,
            csrf=csrf,
        )
        _, events, _ = self.request(
            "GET",
            f"/api/agent-sessions/{session_id}/events",
            cookie=cookie,
            raw=True,
        )

        self.assertNotIn("approval.request", [event["kind"] for event in events])
        self.assertEqual(self.provider.approval, (session_id, "approval-1", False))

    def test_expired_approval_cannot_be_replayed(self):
        self.provider.approval_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
        cookie, csrf, session = self.create_session()
        session_id = session["id"]
        self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/messages",
            {"message": "hello"},
            cookie=cookie,
            csrf=csrf,
        )
        self.request(
            "GET",
            f"/api/agent-sessions/{session_id}/events",
            cookie=cookie,
            raw=True,
        )

        status, payload, _ = self.request(
            "POST",
            f"/api/agent-sessions/{session_id}/approvals/approval-1",
            {"approved": True},
            cookie=cookie,
            csrf=csrf,
        )

        self.assertEqual(status, 410)
        self.assertEqual(payload["error"], "approval request has expired")
        self.assertEqual(self.provider.approval, (session_id, "approval-1", False))

    def test_unknown_sessions_and_oversized_requests_are_rejected(self):
        cookie, csrf, _ = self.authenticate()

        status, _, _ = self.request(
            "POST",
            "/api/agent-sessions/missing/interrupt",
            {},
            cookie=cookie,
            csrf=csrf,
        )
        self.assertEqual(status, 404)

        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        connection.putrequest("POST", "/api/agent-sessions")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
        connection.putheader("Cookie", cookie)
        connection.putheader("X-CSRF-Token", csrf)
        connection.endheaders()
        response = connection.getresponse()
        try:
            self.assertEqual(response.status, 422)
        finally:
            response.read()
            connection.close()

    def test_agent_session_is_owned_by_the_cookie_that_created_it(self):
        _, _, session = self.create_session()
        other_cookie, other_csrf, _ = self.authenticate()

        status, payload, _ = self.request(
            "POST",
            f"/api/agent-sessions/{session['id']}/interrupt",
            {},
            cookie=other_cookie,
            csrf=other_csrf,
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "agent session was not found")

    def request(self, method, path, payload=None, cookie=None, csrf=None, raw=False):
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        if csrf:
            headers["X-CSRF-Token"] = csrf
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(f"{self.base_url}{path}", data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                body = response.read().decode("utf-8")
                parsed = parse_sse(body) if raw else json.loads(body)
                return response.status, parsed, response.headers
        except HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8")), error.headers
            finally:
                error.close()


class AgentUnavailableFallbackTests(unittest.TestCase):
    def test_unavailable_agents_do_not_disable_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            provider = FakeWebProvider(available=False, detail="token=do-not-return-this")
            server = create_server(
                ProfileStore(workspace / "config.json"),
                port=0,
                gateway=AgentGateway({"fake": provider}),
                agent_workspace=workspace,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(f"{base_url}/api/agents", timeout=2) as response:
                    agents = json.loads(response.read())["agents"]
                request = Request(
                    f"{base_url}/api/analyze",
                    data=json.dumps({"question": "Why did retention fall?"}).encode(),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urlopen(request, timeout=2) as response:
                    analysis = json.loads(response.read())
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

            self.assertFalse(agents[0]["available"])
            self.assertNotIn("do-not-return-this", json.dumps(agents))
            self.assertEqual(analysis["validation"]["status"], "supported")


def parse_sse(body):
    events = []
    for block in body.strip().split("\n\n"):
        data = "\n".join(line[6:] for line in block.splitlines() if line.startswith("data: "))
        if data:
            events.append(json.loads(data))
    return events


if __name__ == "__main__":
    unittest.main()
