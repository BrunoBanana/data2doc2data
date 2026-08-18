from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
import tempfile
import threading
import unittest

from data2doc2data.agents.gateway import AgentGateway, NotAuthenticated, ProviderUnavailable
from data2doc2data.agents.workbuddy import (
    WorkBuddyProvider,
    _decode_sse_response,
    _is_authentication_error,
    _unwrap_data,
)


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
                    result_event = (
                        'data: {"jsonrpc":"2.0","id":' + str(payload.get("id"))
                        + ',"result":{"stopReason":"end_turn"}}\n\n'
                    )
                    self._sse_body(stream + result_event)
                    return
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

            def _sse_body(self, body):
                encoded = body.encode("utf-8")
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
            self.assertEqual(preview, "codebuddy --serve --model hy3 --port 8765 --session-id session-id")
            self.assertNotIn("yolo", preview)
            self.assertNotIn("dangerously", preview)


class WorkBuddyProtocolHelpersTests(unittest.TestCase):
    def test_unwrap_data_strips_the_envelope_only_when_plain(self):
        self.assertEqual(_unwrap_data({"data": {"ok": True}}), {"ok": True})
        rpc = {"data": {"id": 1}, "jsonrpc": "2.0"}
        self.assertEqual(_unwrap_data(rpc), rpc)
        self.assertEqual(_unwrap_data("literal"), "literal")

    def test_decode_sse_response_returns_the_last_data_event(self):
        body = 'data: {"first": 1}\n\ndata: {"second": 2}\n\n'

        self.assertEqual(_decode_sse_response(body), {"second": 2})

    def test_decode_sse_response_rejects_empty_stream(self):
        with self.assertRaises(ValueError):
            _decode_sse_response("no data here")

    def test_authentication_error_is_detected_by_category_and_message(self):
        self.assertTrue(_is_authentication_error({"data": {"category": "auth"}}))
        self.assertTrue(_is_authentication_error({"message": "Authentication required"}))
        self.assertFalse(_is_authentication_error({"message": "other"}))

    def test_normalize_update_maps_tool_calls_and_results(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = WorkBuddyProvider(Path(directory))

            call = provider._normalize_update(
                {"sessionUpdate": "tool_call", "toolCallId": "call-1", "title": "Bash", "rawInput": {"cmd": "ls"}}
            )
            self.assertEqual(call.kind, "tool.call")
            self.assertEqual(call.payload["call_id"], "call-1")
            self.assertEqual(call.payload["name"], "Bash")

            result = provider._normalize_update(
                {"sessionUpdate": "tool_call_update", "toolCallId": "call-1", "rawOutput": "ok", "status": "completed"}
            )
            self.assertEqual(result.kind, "tool.result")
            self.assertFalse(result.payload["error"])

    def test_normalize_update_maps_plan_and_ignores_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = WorkBuddyProvider(Path(directory))

            plan = provider._normalize_update({"sessionUpdate": "agent_thought_chunk", "content": {"text": "thinking"}})
            self.assertEqual(plan.kind, "plan.delta")
            self.assertEqual(plan.payload["text"], "thinking")

            self.assertIsNone(provider._normalize_update({"sessionUpdate": "unknown_kind"}))

    def test_normalize_update_rejects_malformed_message_chunk(self):
        with tempfile.TemporaryDirectory() as directory:
            provider = WorkBuddyProvider(Path(directory))

            with self.assertRaises(Exception):
                provider._normalize_update({"sessionUpdate": "agent_message_chunk", "content": {"type": "text"}})


if __name__ == "__main__":
    unittest.main()
