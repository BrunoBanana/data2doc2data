"""Codex App Server adapter over newline-delimited JSON-RPC on stdio."""

from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Full, Queue
import shutil
import subprocess
import threading
from typing import Mapping

from .base import AgentEvent, AgentSession, ProviderStatus
from .gateway import InvalidProviderPayload, ProviderUnavailable
from ._shared import emit_provider_error, minimal_environment, required_text, validate_session


class _ReaderFailure:
    pass


READER_FAILURE = _ReaderFailure()


class CodexProvider:
    name = "codex"

    def __init__(
        self,
        workspace: Path,
        executable: str = "codex",
        version_command: tuple[str, ...] | None = None,
        app_server_command: tuple[str, ...] | None = None,
        request_timeout: float = 10.0,
        event_timeout: float | None = None,
    ) -> None:
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError("Codex workspace must be an existing directory")
        if request_timeout <= 0:
            raise ValueError("Codex request timeout must be positive")
        if event_timeout is not None and event_timeout <= 0:
            raise ValueError("Codex event timeout must be positive")
        self.executable = executable
        self.version_command = version_command or (executable, "--version")
        self.start_command = app_server_command or (executable, "app-server", "--stdio")
        self.request_timeout = request_timeout
        self.event_timeout = event_timeout if event_timeout is not None else 120.0
        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._reconnect_lock = threading.Lock()
        self._next_request_id = 1
        self._pending: dict[int, Queue[object]] = {}
        self._event_queues: dict[str, Queue[AgentEvent]] = {}
        self._active_turns: dict[str, str] = {}
        self._approvals: dict[str, tuple[object, str]] = {}
        self._closing = False
        self._version: str | None = None

    def detect(self) -> ProviderStatus:
        executable_path = shutil.which(self.executable)
        if executable_path is None:
            return ProviderStatus(False, False, detail="codex executable was not found")
        connected = self._process is not None and self._process.poll() is None
        if self._version is None:
            try:
                completed = subprocess.run(
                    self.version_command,
                    cwd=self.workspace,
                    env=minimal_environment("CODEX_HOME"),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    timeout=min(self.request_timeout, 3.0),
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise TimeoutError("Codex version detection timed out") from error
            except OSError:
                return ProviderStatus(False, False, detail="codex version could not be read")
            self._version = completed.stdout.strip()[:200] or None
            compatible = completed.returncode == 0 and bool(self._version and "codex" in self._version.lower())
        else:
            compatible = "codex" in self._version.lower()
        return ProviderStatus(
            available=True,
            connected=connected,
            version=self._version,
            compatible=compatible,
            detail=None if compatible else "codex app-server version is incompatible",
        )

    def connect(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self._closing = False
        try:
            self._process = subprocess.Popen(
                self.start_command,
                cwd=self.workspace,
                env=minimal_environment("CODEX_HOME"),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError as error:
            self._process = None
            raise ProviderUnavailable(self.name, "Codex App Server could not start") from error
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()
        result = self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "data2doc2data",
                    "title": "Data2Doc2Data",
                    "version": "3.0.0",
                },
                "capabilities": {},
            },
        )
        if not isinstance(result, Mapping):
            raise InvalidProviderPayload(self.name, "Codex initialize response is invalid")
        self._notify("initialized", {})

    def create_session(self, workspace: Path, resume_id: str | None = None) -> str:
        self._require_connected()
        resolved_workspace = workspace.expanduser().resolve()
        if resolved_workspace != self.workspace:
            raise ValueError("Codex session workspace differs from the approved workspace")
        common_params = {
            "cwd": str(self.workspace),
            "approvalPolicy": "on-request",
            "approvalsReviewer": "user",
            "sandbox": "read-only",
        }
        if resume_id is None:
            result = self._request("thread/start", {**common_params, "ephemeral": False})
        else:
            result = self._request("thread/resume", {**common_params, "threadId": resume_id})
        thread_id = _nested_text(result, "thread", "id")
        if not thread_id:
            raise InvalidProviderPayload(self.name, "Codex thread response is missing its ID")
        self._event_queues.setdefault(thread_id, Queue())
        return thread_id

    def stream_turn(self, session: AgentSession, message: str):
        try:
            self._validate_session(session)
        except ProviderUnavailable:
            self._reconnect_session(session)
        result = self._request(
            "turn/start",
            {
                "threadId": session.provider_session_id,
                "input": [{"type": "text", "text": message}],
                "cwd": str(self.workspace),
                "approvalPolicy": "on-request",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
            },
        )
        turn_id = _nested_text(result, "turn", "id")
        if not turn_id:
            raise InvalidProviderPayload(self.name, "Codex turn response is missing its ID")
        self._active_turns[session.provider_session_id] = turn_id
        event_queue = self._event_queues[session.provider_session_id]
        while True:
            try:
                event = event_queue.get(timeout=self.event_timeout)
            except Empty as error:
                raise TimeoutError("Codex event stream timed out") from error
            yield event
            if event.kind in {"turn.completed", "turn.cancelled", "turn.error", "provider.error"}:
                self._active_turns.pop(session.provider_session_id, None)
                return

    def _reconnect_session(self, session: AgentSession) -> None:
        with self._reconnect_lock:
            if self._process is not None and self._process.poll() is None:
                self._validate_session(session)
                return
            previous = self._process
            self._process = None
            if self._reader_thread is not None:
                self._reader_thread.join(timeout=2)
            self._reader_thread = None
            if previous is not None:
                if previous.stdin is not None:
                    previous.stdin.close()
                if previous.stdout is not None:
                    previous.stdout.close()
            self._approvals.clear()
            self._active_turns.clear()
            event_queue = self._event_queues.get(session.provider_session_id)
            if event_queue is not None:
                while True:
                    try:
                        event_queue.get_nowait()
                    except Empty:
                        break
                event_queue.put(
                    AgentEvent(
                        "provider.status",
                        {"state": "reconnecting", "detail": "Codex App Server is restarting"},
                    )
                )
            self.connect()
            resumed = self.create_session(self.workspace, session.provider_session_id)
            if resumed != session.provider_session_id:
                raise InvalidProviderPayload(self.name, "Codex resumed a different thread")
            if event_queue is not None:
                event_queue.put(
                    AgentEvent(
                        "provider.status",
                        {"state": "connected", "detail": "Codex thread resumed"},
                    )
                )

    def decide_approval(
        self,
        session: AgentSession,
        approval_id: str,
        approved: bool,
    ) -> None:
        self._validate_session(session)
        try:
            request_id, method = self._approvals.pop(approval_id)
        except KeyError as error:
            raise ValueError("Codex approval is no longer pending") from error
        decision = "accept" if approved else "decline"
        self._write_message({"id": request_id, "result": {"decision": decision}})
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            raise InvalidProviderPayload(self.name, "Codex approval method is invalid")

    def interrupt(self, session: AgentSession) -> None:
        self._validate_session(session)
        turn_id = self._active_turns.get(session.provider_session_id)
        if turn_id is None:
            return
        self._request(
            "turn/interrupt",
            {"threadId": session.provider_session_id, "turnId": turn_id},
        )

    def close(self) -> None:
        self._closing = True
        process = self._process
        self._process = None
        self._approvals.clear()
        self._active_turns.clear()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)
        self._reader_thread = None
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()

    def _request(self, method: str, params: dict[str, object]) -> object:
        self._require_connected()
        with self._state_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            response_queue: Queue[object] = Queue(maxsize=1)
            self._pending[request_id] = response_queue
        try:
            self._write_message({"id": request_id, "method": method, "params": params})
            try:
                response = response_queue.get(timeout=self.request_timeout)
            except Empty as error:
                raise TimeoutError(f"Codex request timed out: {method}") from error
            if response is READER_FAILURE:
                raise ProviderUnavailable(self.name, "Codex App Server exited")
            if not isinstance(response, Mapping):
                raise InvalidProviderPayload(self.name, "Codex response is invalid")
            if "error" in response:
                raise ProviderUnavailable(self.name, f"Codex request failed: {method}")
            if "result" not in response:
                raise InvalidProviderPayload(self.name, "Codex response is missing a result")
            return response["result"]
        finally:
            with self._state_lock:
                self._pending.pop(request_id, None)

    def _notify(self, method: str, params: dict[str, object]) -> None:
        self._write_message({"method": method, "params": params})

    def _write_message(self, message: dict[str, object]) -> None:
        process = self._process
        if process is None or process.poll() is not None or process.stdin is None:
            raise ProviderUnavailable(self.name, "Codex App Server is not connected")
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            with self._write_lock:
                process.stdin.write(encoded)
                process.stdin.flush()
        except (OSError, BrokenPipeError) as error:
            raise ProviderUnavailable(self.name, "Codex App Server connection closed") from error

    def _reader_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError
                    self._route_message(message)
                except (json.JSONDecodeError, ValueError, InvalidProviderPayload):
                    self._emit_provider_error("Codex returned an invalid protocol message", "invalidPayload")
                    if process.poll() is None:
                        process.terminate()
                    return
        finally:
            self._reader_ended()

    def _route_message(self, message: dict[str, object]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        if method is None and request_id is not None:
            with self._state_lock:
                pending = self._pending.get(request_id)
            if pending is not None:
                pending.put(message)
            return
        if not isinstance(method, str):
            raise InvalidProviderPayload(self.name, "Codex message method is invalid")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise InvalidProviderPayload(self.name, "Codex message params are invalid")
        if request_id is not None:
            self._route_server_request(request_id, method, params)
            return
        for event in self._notification_events(method, params):
            self._enqueue(params.get("threadId"), event)

    def _route_server_request(self, request_id: object, method: str, params: dict[str, object]) -> None:
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            self._write_message({"id": request_id, "error": {"code": -32601, "message": "method not supported"}})
            return
        approval_id = params.get("approvalId") or params.get("itemId") or f"codex-{request_id}"
        if not isinstance(approval_id, str) or not approval_id or approval_id in self._approvals:
            raise InvalidProviderPayload(self.name, "Codex approval ID is invalid")
        self._approvals[approval_id] = (request_id, method)
        operation = "command" if "commandExecution" in method else "write"
        payload: dict[str, object] = {
            "request_id": approval_id,
            "operation": operation,
        }
        for source, target in (
            ("command", "command"),
            ("cwd", "working_directory"),
            ("reason", "reason"),
        ):
            if isinstance(params.get(source), str):
                payload[target] = params[source]
        grant_root = params.get("grantRoot")
        if isinstance(grant_root, str):
            payload["target_paths"] = [grant_root]
        self._enqueue(params.get("threadId"), AgentEvent("approval.request", payload))

    def _notification_events(self, method: str, params: dict[str, object]) -> list[AgentEvent]:
        if method == "item/agentMessage/delta":
            return [AgentEvent("message.delta", {"text": required_text(self.name, params, "delta")})]
        if method == "item/plan/delta":
            return [AgentEvent("plan.delta", {"text": required_text(self.name, params, "delta")})]
        if method in {"item/commandExecution/outputDelta", "item/fileChange/outputDelta"}:
            return [AgentEvent("command.output", {"text": required_text(self.name, params, "delta")})]
        if method == "item/fileChange/patchUpdated":
            events = []
            changes = params.get("changes")
            if not isinstance(changes, list):
                raise InvalidProviderPayload(self.name, "Codex file changes are invalid")
            for change in changes:
                if not isinstance(change, dict):
                    raise InvalidProviderPayload(self.name, "Codex file change is invalid")
                events.append(
                    AgentEvent(
                        "file.diff",
                        {
                            "path": required_text(self.name, change, "path"),
                            "diff": required_text(self.name, change, "diff"),
                        },
                    )
                )
            return events
        if method == "turn/completed":
            turn = params.get("turn")
            if not isinstance(turn, dict):
                raise InvalidProviderPayload(self.name, "Codex completed turn is invalid")
            turn_id = required_text(self.name, turn, "id")
            status = turn.get("status")
            if status == "failed":
                payload: dict[str, object] = {
                    "turn_id": turn_id,
                    "message": "Codex turn failed",
                    "code": "turnFailed",
                }
                error = turn.get("error")
                if isinstance(error, Mapping):
                    message = error.get("message")
                    code = error.get("codexErrorInfo")
                    if isinstance(message, str) and message.strip():
                        payload["message"] = message.strip()[:1000]
                    if isinstance(code, str) and code.strip():
                        payload["code"] = code.strip()[:100]
                return [AgentEvent("turn.error", payload)]
            if status == "interrupted":
                return [AgentEvent("turn.cancelled", {"turn_id": turn_id})]
            return [AgentEvent("turn.completed", {"turn_id": turn_id})]
        return []

    def _enqueue(self, thread_id: object, event: AgentEvent) -> None:
        if not isinstance(thread_id, str) or thread_id not in self._event_queues:
            return
        self._event_queues[thread_id].put(event)

    def _emit_provider_error(self, message: str, code: str) -> None:
        emit_provider_error(self._event_queues, message, code)

    def _reader_ended(self) -> None:
        with self._state_lock:
            pending = tuple(self._pending.values())
        for response_queue in pending:
            try:
                response_queue.put_nowait(READER_FAILURE)
            except Full:
                pass
        self._approvals.clear()
        if not self._closing:
            self._emit_provider_error("Codex App Server exited unexpectedly", "providerExited")

    def _require_connected(self) -> None:
        if self._process is None or self._process.poll() is not None:
            raise ProviderUnavailable(self.name, "Codex App Server is not connected")

    def _validate_session(self, session: AgentSession) -> None:
        self._require_connected()
        validate_session(self.name, session, self.workspace, self._event_queues)


def _nested_text(value: object, *keys: str) -> str | None:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current if isinstance(current, str) and current else None
