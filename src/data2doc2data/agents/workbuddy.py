"""Tencent WorkBuddy/CodeBuddy adapter using its public ACP-over-SSE API."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
import ipaddress
import json
from pathlib import Path
from queue import Empty, Queue
import re
import random
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener
import uuid

from .base import AgentEvent, AgentSession, ProviderStatus
from .gateway import InvalidProviderPayload, NotAuthenticated, ProviderUnavailable
from ._shared import emit_provider_error, minimal_environment, required_text, validate_session


MAX_HTTP_BYTES = 1_000_000


class WorkBuddyProvider:
    name = "workbuddy"

    def __init__(
        self,
        workspace: Path,
        endpoint: str | None = None,
        executable: str = "codebuddy",
        model: str = "hy3",
        request_timeout: float = 10.0,
        reconnect_delays: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError("WorkBuddy workspace must be an existing directory")
        if request_timeout <= 0:
            raise ValueError("WorkBuddy request timeout must be positive")
        if not reconnect_delays or any(delay < 0 for delay in reconnect_delays):
            raise ValueError("WorkBuddy reconnect delays must be non-negative")
        self.executable = executable
        self.model = model
        self.request_timeout = request_timeout
        self.reconnect_delays = reconnect_delays
        self.endpoint = _validate_endpoint(endpoint) if endpoint is not None else None
        self._configured_endpoint = self.endpoint is not None
        self._opener = build_opener(ProxyHandler({}))
        self._owned_process: subprocess.Popen[bytes] | None = None
        self._serve_password: str | None = None
        self._serve_log_path: Path | None = None
        self._connection_id: str | None = None
        self._session_token: str | None = None
        self._sse_response = None
        self._sse_thread: threading.Thread | None = None
        self._closing = False
        self._stop_reconnect = threading.Event()
        self._connection_lock = threading.Lock()
        self._connected_event = threading.Event()
        self._next_request_id = 1
        self._request_lock = threading.Lock()
        self._event_queues: dict[str, Queue[AgentEvent]] = {}
        self._approvals: dict[str, tuple[object, list[dict[str, object]]]] = {}
        self._version: str | None = None
        self._agent_capabilities: dict[str, object] = {}

    def start_command(self, port: int, session_id: str) -> tuple[str, ...]:
        return (
            self.executable,
            "--serve",
            "--model",
            self.model,
            "--port",
            str(port),
            "--session-id",
            session_id,
        )

    def detect(self) -> ProviderStatus:
        connected = self._connection_id is not None and self._connected_event.is_set()
        if self.endpoint is not None and self._health_available():
            return ProviderStatus(True, connected, version=self._version, authenticated=True)
        if self._configured_endpoint:
            return ProviderStatus(
                True,
                False,
                version=self._version,
                detail="configured CodeBuddy endpoint is unavailable",
            )
        executable_path = shutil.which(self.executable)
        if executable_path is None:
            return ProviderStatus(False, False, detail="codebuddy executable was not found")
        if self._version is None:
            try:
                completed = subprocess.run(
                    (self.executable, "--version"),
                    cwd=self.workspace,
                    env=_minimal_environment(),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=min(self.request_timeout, 3.0),
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("CodeBuddy version detection timed out") from error
            except OSError:
                return ProviderStatus(False, False, detail="codebuddy version could not be read")
            self._version = completed.stdout.strip()[:200] or None
            compatible = completed.returncode == 0 and bool(
                self._version and ("codebuddy" in self._version.lower() or self._version[0].isdigit())
            )
        else:
            compatible = True
        return ProviderStatus(
            True,
            connected,
            version=self._version,
            compatible=compatible,
            detail=None if compatible else "CodeBuddy HTTP API version is incompatible",
        )

    def connect(self) -> None:
        if self._connection_id is not None:
            return
        self._closing = False
        self._stop_reconnect.clear()
        try:
            if self.endpoint is None:
                self._start_owned_server()
            if not self._health_available():
                raise ProviderUnavailable(self.name, "CodeBuddy health endpoint is unavailable")
            payload = self._json_request("POST", "/api/v1/acp/connect", {})
            data = _unwrap_data(payload)
            if not isinstance(data, Mapping):
                raise InvalidProviderPayload(self.name, "CodeBuddy connection response is invalid")
            connection_id = data.get("connectionId")
            session_token = data.get("sessionToken")
            if not isinstance(connection_id, str) or not connection_id:
                raise InvalidProviderPayload(self.name, "CodeBuddy connection ID is missing")
            if not isinstance(session_token, str) or not session_token:
                raise InvalidProviderPayload(self.name, "CodeBuddy session token is missing")
            self._connection_id = connection_id
            self._session_token = session_token
            self._sse_thread = threading.Thread(target=self._sse_loop, daemon=True)
            self._sse_thread.start()
            initialized = self._rpc(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientInfo": {
                        "name": "data2doc2data",
                        "title": "Data2Doc2Data",
                        "version": "3.1.0",
                    },
                    "clientCapabilities": {},
                },
            )
            if isinstance(initialized, Mapping) and isinstance(initialized.get("agentCapabilities"), dict):
                self._agent_capabilities = dict(initialized["agentCapabilities"])
            self._connected_event.set()
        except Exception:
            self.close()
            raise

    def create_session(self, workspace: Path, resume_id: str | None = None) -> str:
        self._require_connected()
        resolved_workspace = workspace.expanduser().resolve()
        if resolved_workspace != self.workspace:
            raise ValueError("WorkBuddy session workspace differs from the approved workspace")
        if resume_id is None:
            result = self._rpc(
                "session/new",
                {"cwd": str(self.workspace), "mcpServers": [], "additionalDirectories": []},
            )
        else:
            try:
                result = self._rpc("session/resume", {"sessionId": resume_id, "cwd": str(self.workspace)})
            except ProviderUnavailable:
                if not self._agent_capabilities.get("loadSession"):
                    raise
                result = self._rpc(
                    "session/load",
                    {"sessionId": resume_id, "cwd": str(self.workspace), "mcpServers": []},
                )
        session_id = result.get("sessionId") if isinstance(result, Mapping) else None
        if not isinstance(session_id, str) or not session_id:
            raise InvalidProviderPayload(self.name, "WorkBuddy session ID is missing")
        self._event_queues.setdefault(session_id, Queue())
        return session_id

    def stream_turn(self, session: AgentSession, message: str):
        self._validate_session(session)
        with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
        event_queue = self._event_queues[session.provider_session_id]
        try:
            response = self._open_prompt(request_id, session.provider_session_id, message)
        except Exception as error:
            raise ProviderUnavailable(self.name, "WorkBuddy prompt could not start") from error
        stop_reason = None
        try:
            for raw_line in response:
                for queued in self._drain_queue(event_queue):
                    yield queued
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                try:
                    event_message = json.loads(line[5:].lstrip())
                except json.JSONDecodeError:
                    continue
                event_message = _unwrap_data(event_message)
                if not isinstance(event_message, dict):
                    continue
                if event_message.get("id") == request_id and "result" in event_message:
                    result = event_message["result"]
                    if isinstance(result, Mapping):
                        stop_reason = result.get("stopReason")
                    continue
                method = event_message.get("method")
                params = event_message.get("params", {})
                if event_message.get("id") is not None:
                    if method == "session/request_permission" and isinstance(params, dict):
                        self._route_permission_request(event_message["id"], method, params)
                    continue
                if method == "session/update" and isinstance(params, dict):
                    update = params.get("update")
                    if isinstance(update, dict):
                        event = self._normalize_update(update)
                        if event is not None:
                            yield event
        finally:
            response.close()
        for queued in self._drain_queue(event_queue):
            yield queued
        if stop_reason in {"cancelled", "canceled"}:
            yield AgentEvent("turn.cancelled", {"reason": str(stop_reason)})
        else:
            yield AgentEvent("turn.completed", {})

    def _open_prompt(self, request_id: int, session_id: str, message: str):
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": message}],
            },
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self.endpoint}/api/v1/acp",
            data=encoded,
            method="POST",
            headers=self._headers(accept="application/json, text/event-stream", content_type=True),
        )
        return self._opener.open(request, timeout=max(60.0, self.request_timeout))

    @staticmethod
    def _drain_queue(queue: Queue[object]):
        drained = []
        while True:
            try:
                drained.append(queue.get_nowait())
            except Empty:
                return drained

    def decide_approval(
        self,
        session: AgentSession,
        approval_id: str,
        approved: bool,
    ) -> None:
        self._validate_session(session)
        try:
            request_id, options = self._approvals.pop(approval_id)
        except KeyError as error:
            raise ValueError("WorkBuddy approval is no longer pending") from error
        desired = ("allow", "approve") if approved else ("reject", "deny")
        selected = next(
            (
                option.get("optionId")
                for option in options
                if isinstance(option.get("optionId"), str)
                and any(term in str(option.get("kind", "")).lower() for term in desired)
            ),
            None,
        )
        if approved and selected is None:
            raise InvalidProviderPayload(self.name, "WorkBuddy did not offer an approval option")
        outcome = {"outcome": "selected", "optionId": selected} if selected is not None else {"outcome": "cancelled"}
        self._post_rpc_message(
            {"jsonrpc": "2.0", "id": request_id, "result": {"outcome": outcome}},
            allow_empty=True,
        )

    def interrupt(self, session: AgentSession) -> None:
        self._validate_session(session)
        self._cancel_session(session.provider_session_id)

    def _cancel_session(self, session_id: str) -> None:
        self._post_rpc_message(
            {
                "jsonrpc": "2.0",
                "method": "session/cancel",
                "params": {"sessionId": session_id},
            }
        )

    def close(self) -> None:
        self._closing = True
        self._stop_reconnect.set()
        if self.endpoint is not None and self._connection_id is not None:
            try:
                self._json_request("DELETE", "/api/v1/acp")
            except (ProviderUnavailable, InvalidProviderPayload):
                pass
        if self._sse_response is not None:
            self._sse_response.close()
        if self._sse_thread is not None:
            self._sse_thread.join(timeout=2)
        self._sse_response = None
        self._sse_thread = None
        self._connection_id = None
        self._session_token = None
        self._connected_event.clear()
        self._approvals.clear()
        self._agent_capabilities.clear()
        process = self._owned_process
        self._owned_process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._serve_password = None
        if self._serve_log_path is not None:
            self._serve_log_path.unlink(missing_ok=True)
            self._serve_log_path = None
        if not self._configured_endpoint:
            self.endpoint = None

    def _rpc(self, method: str, params: dict[str, object]) -> object:
        with self._request_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
        payload = self._post_rpc_message({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = _unwrap_data(payload)
        if not isinstance(response, Mapping):
            raise InvalidProviderPayload(self.name, "WorkBuddy JSON-RPC response is invalid")
        error = response.get("error")
        if isinstance(error, Mapping) and _is_authentication_error(error):
            raise NotAuthenticated(self.name, "WorkBuddy authentication is required")
        if error is not None:
            raise ProviderUnavailable(self.name, f"WorkBuddy request failed: {method}")
        if response.get("id") != request_id or "result" not in response:
            raise InvalidProviderPayload(self.name, "WorkBuddy JSON-RPC response does not match the request")
        return response["result"]

    def _post_rpc_message(self, payload: dict[str, object], allow_empty: bool = False) -> object:
        return self._json_request(
            "POST",
            "/api/v1/acp",
            payload,
            accept="application/json, text/event-stream",
            allow_empty=allow_empty,
        )

    def _sse_loop(self) -> None:
        attempt = 0
        while not self._closing:
            try:
                request = Request(
                    f"{self.endpoint}/api/v1/acp",
                    method="GET",
                    headers=self._headers(accept="text/event-stream"),
                )
                response = self._opener.open(request, timeout=max(60.0, self.request_timeout))
                self._sse_response = response
                data_lines = []
                data_size = 0
                for raw_line in response:
                    line = raw_line.decode("utf-8").rstrip("\r\n")
                    if not line:
                        if data_lines:
                            self._route_sse_data("\n".join(data_lines))
                            data_lines = []
                            data_size = 0
                        continue
                    if line.startswith("data:"):
                        value = line[5:].lstrip()
                        data_size += len(value.encode("utf-8"))
                        if data_size > MAX_HTTP_BYTES:
                            raise InvalidProviderPayload(self.name, "WorkBuddy SSE event is too large")
                        data_lines.append(value)
                if self._closing:
                    return
            except Exception:
                if self._closing:
                    return
            finally:
                self._sse_response = None
            self._clear_connection()
            self._emit_provider_status("reconnecting", "WorkBuddy event stream closed; reconnecting")
            while not self._closing:
                base_delay = self.reconnect_delays[min(attempt, len(self.reconnect_delays) - 1)]
                delay = base_delay * random.uniform(0.8, 1.2)
                attempt += 1
                if self._stop_reconnect.wait(delay):
                    return
                try:
                    self._restore_connection()
                    attempt = 0
                    self._connected_event.set()
                    self._emit_provider_status("connected", "WorkBuddy sessions resumed")
                    break
                except NotAuthenticated:
                    self._clear_connection()
                    self._emit_provider_status("auth_required", "WorkBuddy authentication is required")
                    return
                except InvalidProviderPayload:
                    self._clear_connection()
                    self._emit_provider_status("failed", "WorkBuddy connection protocol is incompatible")
                    return
                except (ProviderUnavailable, OSError, TimeoutError):
                    self._clear_connection()
                    continue

    def _restore_connection(self) -> None:
        if not self._health_available():
            raise ProviderUnavailable(self.name, "CodeBuddy health endpoint is unavailable")
        payload = self._json_request("POST", "/api/v1/acp/connect", {})
        data = _unwrap_data(payload)
        if not isinstance(data, Mapping):
            raise InvalidProviderPayload(self.name, "CodeBuddy connection response is invalid")
        connection_id = data.get("connectionId")
        session_token = data.get("sessionToken")
        if not isinstance(connection_id, str) or not connection_id:
            raise InvalidProviderPayload(self.name, "CodeBuddy connection ID is missing")
        if not isinstance(session_token, str) or not session_token:
            raise InvalidProviderPayload(self.name, "CodeBuddy session token is missing")
        with self._connection_lock:
            self._connection_id = connection_id
            self._session_token = session_token
        initialized = self._rpc(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {
                    "name": "data2doc2data",
                    "title": "Data2Doc2Data",
                    "version": "3.1.0",
                },
                "clientCapabilities": {},
            },
        )
        if isinstance(initialized, Mapping) and isinstance(initialized.get("agentCapabilities"), dict):
            self._agent_capabilities = dict(initialized["agentCapabilities"])
        for session_id in tuple(self._event_queues):
            try:
                resumed = self._rpc(
                    "session/resume",
                    {"sessionId": session_id, "cwd": str(self.workspace)},
                )
            except ProviderUnavailable:
                if not self._agent_capabilities.get("loadSession"):
                    raise
                resumed = self._rpc(
                    "session/load",
                    {"sessionId": session_id, "cwd": str(self.workspace), "mcpServers": []},
                )
            restored_id = resumed.get("sessionId") if isinstance(resumed, Mapping) else None
            if restored_id != session_id:
                raise InvalidProviderPayload(self.name, "WorkBuddy resumed a different session")

    def _clear_connection(self) -> None:
        with self._connection_lock:
            self._connection_id = None
            self._session_token = None
            self._connected_event.clear()

    def _emit_provider_status(self, state: str, detail: str) -> None:
        event = AgentEvent("provider.status", {"state": state, "detail": detail})
        for event_queue in self._event_queues.values():
            event_queue.put(event)

    def _route_sse_data(self, data: str) -> None:
        try:
            message = json.loads(data)
        except json.JSONDecodeError as error:
            raise InvalidProviderPayload(self.name, "WorkBuddy SSE payload is invalid") from error
        message = _unwrap_data(message)
        if not isinstance(message, dict):
            raise InvalidProviderPayload(self.name, "WorkBuddy SSE message must be an object")
        method = message.get("method")
        params = message.get("params", {})
        if not isinstance(method, str) or not isinstance(params, dict):
            raise InvalidProviderPayload(self.name, "WorkBuddy SSE method or params are invalid")
        if message.get("id") is not None:
            self._route_permission_request(message["id"], method, params)
            return
        if method != "session/update":
            return
        session_id = params.get("sessionId")
        update = params.get("update")
        if not isinstance(session_id, str) or not isinstance(update, dict):
            raise InvalidProviderPayload(self.name, "WorkBuddy session update is invalid")
        event = self._normalize_update(update)
        if event is not None and session_id in self._event_queues:
            self._event_queues[session_id].put(event)

    def _normalize_update(self, update: dict[str, object]) -> AgentEvent | None:
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content")
            if isinstance(content, dict) and content.get("type") == "text":
                text = content.get("text")
                if isinstance(text, str):
                    return AgentEvent("message.delta", {"text": text})
            raise InvalidProviderPayload(self.name, "WorkBuddy message chunk is invalid")
        if kind in {"agent_thought_chunk", "plan"}:
            content = update.get("content", update.get("entries", ""))
            text = content.get("text") if isinstance(content, dict) else json.dumps(content, ensure_ascii=False)
            return AgentEvent("plan.delta", {"text": str(text)})
        if kind == "tool_call":
            return AgentEvent(
                "tool.call",
                {
                    "call_id": required_text(self.name, update, "toolCallId", nonempty=True),
                    "name": str(update.get("title") or update.get("kind") or "tool"),
                    "arguments": update.get("rawInput", {}),
                },
            )
        if kind == "tool_call_update":
            return AgentEvent(
                "tool.result",
                {
                    "call_id": required_text(self.name, update, "toolCallId", nonempty=True),
                    "result": update.get("rawOutput", update.get("content")),
                    "error": update.get("status") == "failed",
                },
            )
        return None

    def _route_permission_request(
        self,
        request_id: object,
        method: str,
        params: dict[str, object],
    ) -> None:
        if method != "session/request_permission" or not isinstance(request_id, (str, int)):
            raise InvalidProviderPayload(self.name, "WorkBuddy server request is unsupported")
        approval_id = str(request_id)
        options = params.get("options")
        tool_call = params.get("toolCall")
        session_id = params.get("sessionId")
        if not isinstance(options, list) or not all(isinstance(option, dict) for option in options):
            raise InvalidProviderPayload(self.name, "WorkBuddy permission options are invalid")
        if not isinstance(tool_call, dict) or not isinstance(session_id, str):
            raise InvalidProviderPayload(self.name, "WorkBuddy permission tool call is invalid")
        if session_id not in self._event_queues or approval_id in self._approvals:
            raise InvalidProviderPayload(self.name, "WorkBuddy permission request is not routable")
        self._approvals[approval_id] = (request_id, options)
        tool_kind = str(tool_call.get("kind", "tool"))
        operation = {
            "read": "read",
            "edit": "write",
            "delete": "write",
            "write": "write",
            "execute": "command",
        }.get(tool_kind, "tool")
        raw_input = tool_call.get("rawInput")
        command = raw_input.get("command") if isinstance(raw_input, dict) else None
        locations = tool_call.get("locations")
        target_paths = (
            [
                location["path"]
                for location in locations
                if isinstance(location, dict) and isinstance(location.get("path"), str)
            ]
            if isinstance(locations, list)
            else []
        )
        payload: dict[str, object] = {
            "request_id": approval_id,
            "operation": operation,
            "target_paths": target_paths,
        }
        if isinstance(command, str):
            payload["command"] = command
        if session_id in self._event_queues:
            self._event_queues[session_id].put(AgentEvent("approval.request", payload))

    def _health_available(self) -> bool:
        if self.endpoint is None:
            return False
        try:
            payload = self._json_request("GET", "/api/v1/health")
        except (ProviderUnavailable, InvalidProviderPayload):
            return False
        data = _unwrap_data(payload)
        if not isinstance(data, Mapping) or data.get("status") != "ok":
            return False
        version = data.get("version")
        if isinstance(version, str):
            self._version = version[:200]
        return True

    def _start_owned_server(self) -> None:
        if shutil.which(self.executable) is None:
            raise ProviderUnavailable(self.name, "codebuddy executable was not found")
        port = _free_loopback_port()
        session_id = uuid.uuid4().hex
        self._serve_password = None
        log_handle = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            prefix="codebuddy-serve-",
            suffix=".log",
            delete=False,
        )
        self._serve_log_path = Path(log_handle.name)
        try:
            self._owned_process = subprocess.Popen(
                self.start_command(port, session_id),
                cwd=self.workspace,
                env=_minimal_environment(),
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            log_handle.close()
            self._serve_log_path.unlink(missing_ok=True)
            self._serve_log_path = None
            raise ProviderUnavailable(self.name, "CodeBuddy HTTP service could not start") from error
        log_handle.close()
        self.endpoint = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + min(10.0, max(2.0, self.request_timeout))
        while time.monotonic() < deadline:
            if self._owned_process.poll() is not None:
                break
            self._read_serve_password()
            if self._health_available():
                return
            time.sleep(0.05)
        self.close()
        raise ProviderUnavailable(self.name, "CodeBuddy HTTP service did not become ready")

    def _read_serve_password(self) -> None:
        if self._serve_log_path is None or self._serve_password is not None:
            return
        try:
            content = self._serve_log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return
        match = re.search(r"Password\s+([A-Za-z0-9_-]{8,})", content)
        if match:
            self._serve_password = match.group(1)

    def _json_request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
        accept: str = "application/json",
        allow_empty: bool = False,
    ) -> object:
        if self.endpoint is None or not path.startswith("/api/v1/"):
            raise ProviderUnavailable(self.name, "WorkBuddy public endpoint is unavailable")
        encoded = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"{self.endpoint}{path}",
            data=encoded,
            method=method,
            headers=self._headers(accept=accept, content_type=encoded is not None),
        )
        try:
            with self._opener.open(request, timeout=self.request_timeout) as response:
                body = response.read(MAX_HTTP_BYTES + 1)
                content_type = response.headers.get_content_type()
        except HTTPError as error:
            if error.code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
                error.close()
                raise NotAuthenticated(self.name, "WorkBuddy authentication is required") from error
            error.close()
            raise ProviderUnavailable(self.name, f"WorkBuddy HTTP request failed with status {error.code}") from error
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            raise ProviderUnavailable(self.name, "WorkBuddy HTTP request failed") from error
        if len(body) > MAX_HTTP_BYTES:
            raise InvalidProviderPayload(self.name, "WorkBuddy HTTP response is too large")
        if allow_empty and not body:
            return {}
        try:
            text = body.decode("utf-8")
            if content_type == "text/event-stream":
                return _decode_sse_response(text)
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise InvalidProviderPayload(self.name, "WorkBuddy HTTP response is invalid") from error

    def _headers(self, accept: str, content_type: bool = False) -> dict[str, str]:
        headers = {"Accept": accept, "X-CodeBuddy-Request": "1"}
        if content_type:
            headers["Content-Type"] = "application/json"
        if self._connection_id:
            headers["acp-connection-id"] = self._connection_id
        if self._session_token:
            headers["Authorization"] = f"Bearer {self._session_token}"
            headers["acp-session-token"] = self._session_token
        elif self._serve_password:
            headers["Authorization"] = f"Bearer {self._serve_password}"
        return headers

    def _emit_provider_error(self, message: str, code: str) -> None:
        emit_provider_error(self._event_queues, message, code)

    def _require_connected(self) -> None:
        if not self._connected_event.is_set() and not self._closing:
            self._connected_event.wait(timeout=self.request_timeout)
        if self._connection_id is None or not self._connected_event.is_set():
            raise ProviderUnavailable(self.name, "WorkBuddy ACP connection is not established")

    def _validate_session(self, session: AgentSession) -> None:
        self._require_connected()
        validate_session(self.name, session, self.workspace, self._event_queues)


def _validate_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or parsed.hostname is None
    ):
        raise ValueError("WorkBuddy endpoint must be a plain loopback HTTP origin")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as error:
        raise ValueError("WorkBuddy endpoint must use a loopback IP literal") from error
    if not address.is_loopback:
        raise ValueError("WorkBuddy endpoint must use a loopback address")
    return endpoint.rstrip("/")


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _minimal_environment() -> dict[str, str]:
    environment = minimal_environment("CODEBUDDY_HOME")
    environment["SERVER__HOST"] = "127.0.0.1"
    return environment


def _unwrap_data(payload: object) -> object:
    if isinstance(payload, Mapping) and "data" in payload and "jsonrpc" not in payload:
        return payload["data"]
    return payload


def _decode_sse_response(body: str) -> object:
    data_lines: list[str] = []
    messages: list[object] = []
    for line in (*body.splitlines(), ""):
        if not line:
            if data_lines:
                messages.append(json.loads("\n".join(data_lines)))
                data_lines = []
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not messages:
        raise ValueError("WorkBuddy SSE response contains no data event")
    return messages[-1]


def _is_authentication_error(error: Mapping[str, object]) -> bool:
    data = error.get("data")
    category = data.get("category") if isinstance(data, Mapping) else None
    message = error.get("message")
    return category == "auth" or (isinstance(message, str) and "authentication required" in message.lower())
