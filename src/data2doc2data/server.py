"""Loopback-only HTTP companion for local workspace setup and analysis."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Type
from urllib.parse import urlparse

from .agent_api import AgentApiError, AgentWebService, BROWSER_SESSION_SECONDS, TERMINAL_EVENTS
from .agents.gateway import AgentGateway
from .analysis import InputValidationError, analyze, validate_profile
from .config import Profile, ProfileError, ProfileStore
from .demo_scenarios import DemoScenarioCatalog, DemoScenarioError
from .evidence_context import build_source_profile
from .sessions import AuditStore, SessionStore


STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 1_000_000
SESSION_EVENTS_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/events")
SESSION_MESSAGES_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/messages")
SESSION_INTERRUPT_ROUTE = re.compile(r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/interrupt")
SESSION_APPROVAL_ROUTE = re.compile(
    r"/api/agent-sessions/([A-Za-z0-9._:-]{1,200})/approvals/([A-Za-z0-9._:-]{1,200})"
)


class CompanionHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_close(self) -> None:
        if not getattr(self, "_agent_service_closed", False):
            self._agent_service_closed = True
            try:
                self.agent_service.close()
            finally:
                super().server_close()
            return
        super().server_close()


def create_server(
    store: ProfileStore,
    host: str = "127.0.0.1",
    port: int = 8765,
    gateway: AgentGateway | None = None,
    agent_workspace: Path | None = None,
    session_store: SessionStore | None = None,
    audit_store: AuditStore | None = None,
) -> ThreadingHTTPServer:
    """Create a server that is restricted to the IPv4 loopback interface."""
    if host != "127.0.0.1":
        raise ValueError("host must be the loopback address 127.0.0.1")
    workspace = (agent_workspace or Path.cwd()).expanduser().resolve()
    state_directory = store.path.parent
    agent_service = AgentWebService(
        gateway or AgentGateway({}),
        workspace,
        session_store or SessionStore(state_directory / "agent-sessions.json"),
        audit_store or AuditStore(state_directory / "agent-audit.jsonl"),
        store,
    )
    server = CompanionHTTPServer((host, port), _handler_class())
    server.profile_store = store
    server.agent_service = agent_service
    return server


def _handler_class() -> Type[BaseHTTPRequestHandler]:
    class CompanionHandler(BaseHTTPRequestHandler):
        server: ThreadingHTTPServer

        def do_GET(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            path = urlparse(self.path).path
            if path == "/api/agents":
                browser_session, csrf_token = self._agents().browser_sessions.issue()
                self._send_json(
                    HTTPStatus.OK,
                    {"agents": self._agents().list_agents(), "csrf_token": csrf_token},
                    {
                        "Set-Cookie": (
                            f"d2d2d_session={browser_session}; Path=/; Max-Age={BROWSER_SESSION_SECONDS}; "
                            "HttpOnly; SameSite=Strict"
                        )
                    },
                )
                return
            events_match = SESSION_EVENTS_ROUTE.fullmatch(path)
            if events_match:
                try:
                    owner_id = self._agents().browser_sessions.authorize(self.headers.get("Cookie"))
                    event_buffer = self._agents().event_buffer(owner_id, events_match.group(1))
                    self._send_events(event_buffer)
                except AgentApiError as error:
                    self._send_json(error.status, {"error": str(error)})
                return
            if path == "/api/profile":
                try:
                    profile = self._store().load()
                except ProfileError as error:
                    self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {"configured": profile is not None, "profile": profile.to_dict() if profile else None},
                )
                return
            if path == "/api/source-profile":
                try:
                    profile = self._store().load() or Profile.demo()
                    source_profile = build_source_profile(profile)
                except (InputValidationError, ProfileError) as error:
                    self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                    return
                self._send_json(HTTPStatus.OK, source_profile.to_dict())
                return
            if path == "/api/demo-scenarios":
                try:
                    catalog = DemoScenarioCatalog.load()
                except DemoScenarioError:
                    self._send_json(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        {"error": "demo scenario catalog is unavailable"},
                    )
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "default": catalog.default.id,
                        "scenarios": [scenario.to_dict() for scenario in catalog.list()],
                    },
                )
                return
            self._serve_static(path)

        def do_PUT(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            if urlparse(self.path).path != "/api/profile":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
                return
            try:
                profile = Profile.from_dict(self._read_json())
                validate_profile(profile)
                self._store().save(profile)
                self._agents().invalidate_analysis()
            except (InputValidationError, ProfileError, ValueError) as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, {"configured": True, "profile": profile.to_dict()})

        def do_POST(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            path = urlparse(self.path).path
            if path == "/api/agent-sessions":
                self._create_agent_session()
                return
            messages_match = SESSION_MESSAGES_ROUTE.fullmatch(path)
            if messages_match:
                self._start_agent_turn(messages_match.group(1))
                return
            approval_match = SESSION_APPROVAL_ROUTE.fullmatch(path)
            if approval_match:
                self._decide_agent_approval(approval_match.group(1), approval_match.group(2))
                return
            interrupt_match = SESSION_INTERRUPT_ROUTE.fullmatch(path)
            if interrupt_match:
                self._interrupt_agent(interrupt_match.group(1))
                return
            if path != "/api/analyze":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
                return
            try:
                payload = self._read_json()
                question = payload.get("question", "") if isinstance(payload, dict) else ""
                metric_override = payload.get("metric_override") if isinstance(payload, dict) else None
                profile = self._store().load() or Profile.demo()
                result = analyze(question, profile, metric_override, self._store().index_cache_path)
                owner_id = self._optional_agent_owner()
                if owner_id is not None:
                    self._agents().record_analysis(owner_id, result, profile)
                self._send_json(HTTPStatus.OK, result.to_dict())
            except (InputValidationError, ProfileError, ValueError) as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

        def _create_agent_session(self) -> None:
            try:
                owner_id = self._authorize_agent_mutation()
                session = self._agents().create_session(owner_id, self._read_json())
                self._send_json(HTTPStatus.CREATED, {"session": session})
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
            except ValueError as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

        def _start_agent_turn(self, session_id: str) -> None:
            try:
                owner_id = self._authorize_agent_mutation()
                self._agents().start_turn(owner_id, session_id, self._read_json())
                self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
            except ValueError as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

        def _decide_agent_approval(self, session_id: str, approval_id: str) -> None:
            try:
                owner_id = self._authorize_agent_mutation()
                self._agents().decide_approval(owner_id, session_id, approval_id, self._read_json())
                self._send_json(HTTPStatus.OK, {"accepted": True})
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
            except ValueError as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

        def _interrupt_agent(self, session_id: str) -> None:
            try:
                owner_id = self._authorize_agent_mutation()
                payload = self._read_json()
                if not isinstance(payload, dict):
                    raise ValueError("interrupt request must be an object")
                self._agents().interrupt(owner_id, session_id)
                self._send_json(HTTPStatus.ACCEPTED, {"accepted": True})
            except AgentApiError as error:
                self._send_json(error.status, {"error": str(error)})
            except ValueError as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})

        def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Allow", "GET, POST, PUT, OPTIONS")
            self._send_security_headers()
            self.end_headers()

        def _store(self) -> ProfileStore:
            return self.server.profile_store

        def _agents(self) -> AgentWebService:
            return self.server.agent_service

        def _authorize_agent_mutation(self) -> str:
            return self._agents().browser_sessions.authorize_mutation(
                self.headers.get("Cookie"),
                self.headers.get("X-CSRF-Token"),
            )

        def _optional_agent_owner(self) -> str | None:
            try:
                return self._agents().browser_sessions.authorize(self.headers.get("Cookie"))
            except AgentApiError:
                return None

        def _allow_local_origin(self) -> bool:
            expected_host = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            if self.headers.get("Host") == expected_host and origin in {None, f"http://{expected_host}"}:
                return True
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "request must originate from the local companion"})
            return False

        def _read_json(self) -> object:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                raise ValueError("request body is required")
            if length > MAX_REQUEST_BYTES:
                raise ValueError("request body is too large")
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("request body must be JSON") from error

        def _serve_static(self, path: str) -> None:
            requested = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
            if requested not in {"index.html", "app.css", "app.js", "favicon.svg"}:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
                return
            asset = STATIC_ROOT / requested
            if not asset.is_file():
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "setup page is unavailable"})
                return
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
            }[asset.suffix]
            payload = asset.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(
            self,
            status: HTTPStatus,
            payload: object,
            extra_headers: dict[str, str] | None = None,
        ) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for name, value in (extra_headers or {}).items():
                self.send_header(name, value)
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(data)

        def _send_events(self, event_buffer) -> None:
            try:
                last_event_id = int(self.headers.get("Last-Event-ID", "0"))
            except ValueError:
                last_event_id = 0
            if last_event_id < 0:
                last_event_id = 0
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self._send_security_headers()
            self.end_headers()
            self.close_connection = True
            try:
                while True:
                    available = event_buffer.after(last_event_id, timeout=15.0)
                    if not available:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        continue
                    for event_id, event in available:
                        data = json.dumps(
                            {"kind": event.kind, "payload": event.payload},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                        self.wfile.write(f"id: {event_id}\n".encode("ascii"))
                        self.wfile.write(b"data: " + data + b"\n\n")
                        self.wfile.flush()
                        last_event_id = event_id
                        if event.kind in TERMINAL_EVENTS:
                            return
            except (BrokenPipeError, ConnectionResetError):
                return

        def _send_security_headers(self) -> None:
            self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")

        def log_message(self, format: str, *args: object) -> None:
            return

    return CompanionHandler
