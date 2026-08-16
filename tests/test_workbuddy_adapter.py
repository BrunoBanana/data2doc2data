from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
import tempfile
import threading
import unittest

from data2doc2data.agents.gateway import AgentGateway, NotAuthenticated, ProviderUnavailable
from data2doc2data.agents.workbuddy import WorkBuddyProvider


FIXTURE = Path(__file__).parent / "fixtures" / "workbuddy" / "acp-stream.txt"


class FakeWorkBuddy:
    def __init__(
        self,
        health_status=HTTPStatus.OK,
        health_body=None,
        streamable_posts=False,
        session_new_error=None,
    ):
        self.events = Queue()
        self.requests = []
        self.permission_response = None
        self.health_status = health_status
        self.health_body = health_body or {"data": {"status": "ok", "version": "2.106.7"}}
        self.streamable_posts = streamable_posts
        self.session_new_error = session_new_error
        state = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                state.requests.append(("GET", self.path, dict(self.headers)))
                if self.path == "/api/v1/health":
                    self._json(state.health_status, state.health_body)
                    return
                if self.path == "/api/v1/acp":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    while True:
                        event = state.events.get()
                        if event is None:
                            return
                        try:
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                        except BrokenPipeError:
                            return
                    return
                self._json(404, {"error": {"message": "not found"}})

            def do_POST(self):
                state.requests.append(("POST", self.path, dict(self.headers)))
                payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if self.path == "/api/v1/acp/connect":
                    self._json(200, {"data": {"connectionId": "connection-1", "sessionToken": "secret-token"}})
                    return
                if self.path != "/api/v1/acp":
                    self._json(404, {"error": {"message": "not found"}})
                    return
                method = payload.get("method")
                if method == "initialize":
                    result = {"protocolVersion": 1, "agentCapabilities": {"loadSession": True}}
                elif method == "session/new":
                    if state.session_new_error is not None:
                        response = {
                            "data": {
                                "jsonrpc": "2.0",
                                "id": payload.get("id"),
                                "error": state.session_new_error,
                            }
                        }
                        self._json(200, response)
                        return
                    result = {"sessionId": "workbuddy-session"}
                elif method == "session/prompt":
                    stream = FIXTURE.read_text(encoding="utf-8").replace("SESSION", "workbuddy-session")
                    for event in stream.split("\n\n"):
                        if event.strip():
                            state.events.put(event + "\n\n")
                    result = {"stopReason": "end_turn"}
                elif method == "session/cancel":
                    result = {}
                elif "result" in payload and payload.get("id") == "permission-1":
                    state.permission_response = payload["result"]
                    result = {}
                else:
                    result = {}
                response = {"data": {"jsonrpc": "2.0", "id": payload.get("id"), "result": result}}
                if state.streamable_posts:
                    accepted = self.headers.get("Accept", "")
                    if "application/json" not in accepted or "text/event-stream" not in accepted:
                        self._json(406, {"error": {"message": "both response types are required"}})
                        return
                    self._sse(response)
                    return
                self._json(200, response)

            def do_DELETE(self):
                state.requests.append(("DELETE", self.path, dict(self.headers)))
                state.events.put(None)
                self._json(200, {"data": {"disconnected": True}})

            def _json(self, status, payload):
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _sse(self, payload):
                encoded = f"event: message\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format, *args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.events.put(None)
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()


class WorkBuddyAdapterTests(unittest.TestCase):
    def test_public_acp_stream_is_normalized_through_gateway(self):
        fake = FakeWorkBuddy()
        try:
            with tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                provider = WorkBuddyProvider(workspace, endpoint=fake.endpoint, request_timeout=2)
                gateway = AgentGateway({"workbuddy": provider})
                gateway.connect("workbuddy")
                session = gateway.create_session("workbuddy", workspace)

                events = list(gateway.send("workbuddy", session, "hello"))

                self.assertEqual(
                    [event.kind for event in events],
                    ["message.delta", "tool.call", "approval.request", "tool.result", "turn.completed"],
                )
                self.assertEqual(events[0].payload["text"], "hello from workbuddy")
                gateway.decide_approval("workbuddy", session, "permission-1", True)
                self.assertEqual(
                    fake.permission_response,
                    {"outcome": {"outcome": "selected", "optionId": "allow-once"}},
                )
                gateway.interrupt("workbuddy", session)
                gateway.close()

            self.assertTrue(all(path.startswith("/api/v1/") for _, path, _ in fake.requests))
            self.assertTrue(
                all(
                    next(
                        (value for key, value in headers.items() if key.lower() == "x-codebuddy-request"),
                        None,
                    )
                    == "1"
                    for _, _, headers in fake.requests
                )
            )
        finally:
            fake.close()

    def test_non_loopback_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "loopback"):
                WorkBuddyProvider(Path(directory), endpoint="http://example.com:8080")

    def test_streamable_http_post_responses_are_supported(self):
        fake = FakeWorkBuddy(streamable_posts=True)
        try:
            with tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                provider = WorkBuddyProvider(workspace, endpoint=fake.endpoint, request_timeout=2)

                provider.connect()
                session_id = provider.create_session(workspace)

                self.assertEqual(session_id, "workbuddy-session")
                provider.close()
        finally:
            fake.close()

    def test_authentication_rpc_error_is_classified_for_the_web_ui(self):
        fake = FakeWorkBuddy(
            session_new_error={
                "code": -32000,
                "message": "Authentication required",
                "data": {"category": "auth"},
            }
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory)
                provider = WorkBuddyProvider(workspace, endpoint=fake.endpoint, request_timeout=2)
                provider.connect()

                with self.assertRaises(NotAuthenticated):
                    provider.create_session(workspace)

                provider.close()
        finally:
            fake.close()

    def test_http_error_does_not_leak_response_body(self):
        fake = FakeWorkBuddy(
            health_status=HTTPStatus.INTERNAL_SERVER_ERROR,
            health_body={"error": {"message": "password=highly-secret"}},
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                provider = WorkBuddyProvider(Path(directory), endpoint=fake.endpoint)
                gateway = AgentGateway({"workbuddy": provider})

                with self.assertRaises(ProviderUnavailable) as raised:
                    gateway.connect("workbuddy")
                self.assertNotIn("highly-secret", str(raised.exception))
        finally:
            fake.close()

    def test_owned_server_command_contains_no_permission_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = WorkBuddyProvider(Path(directory))

            preview = " ".join(provider.start_command(8765, "session-id"))
            self.assertEqual(preview, "codebuddy --serve --port 8765 --session-id session-id")
            self.assertNotIn("yolo", preview)
            self.assertNotIn("dangerously", preview)


if __name__ == "__main__":
    unittest.main()
