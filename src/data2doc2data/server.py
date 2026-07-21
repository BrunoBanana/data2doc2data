"""Loopback-only HTTP companion for local workspace setup and analysis."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Type
from urllib.parse import urlparse

from .analysis import InputValidationError, analyze, validate_profile
from .config import Profile, ProfileError, ProfileStore


STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 1_000_000


def create_server(store: ProfileStore, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Create a server that is restricted to the IPv4 loopback interface."""
    if host != "127.0.0.1":
        raise ValueError("host must be the loopback address 127.0.0.1")
    server = ThreadingHTTPServer((host, port), _handler_class())
    server.profile_store = store
    return server


def _handler_class() -> Type[BaseHTTPRequestHandler]:
    class CompanionHandler(BaseHTTPRequestHandler):
        server: ThreadingHTTPServer

        def do_GET(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            path = urlparse(self.path).path
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
            except (InputValidationError, ProfileError, ValueError) as error:
                self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, {"configured": True, "profile": profile.to_dict()})

        def do_POST(self) -> None:  # noqa: N802 - HTTP method naming is conventional.
            if not self._allow_local_origin():
                return
            if urlparse(self.path).path != "/api/analyze":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "route not found"})
                return
            try:
                payload = self._read_json()
                question = payload.get("question", "") if isinstance(payload, dict) else ""
                metric_override = payload.get("metric_override") if isinstance(payload, dict) else None
                profile = self._store().load() or Profile.demo()
                self._send_json(HTTPStatus.OK, analyze(question, profile, metric_override).to_dict())
            except (InputValidationError, ProfileError, ValueError) as error:
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

        def _send_json(self, status: HTTPStatus, payload: object) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self._send_security_headers()
            self.end_headers()
            self.wfile.write(data)

        def _send_security_headers(self) -> None:
            self.send_header("Content-Security-Policy", "default-src 'self'; base-uri 'none'; form-action 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")

        def log_message(self, format: str, *args: object) -> None:
            return

    return CompanionHandler
