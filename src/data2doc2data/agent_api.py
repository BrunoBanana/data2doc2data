"""Browser-facing state for the loopback-only local agent API."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
import json
from pathlib import Path
import secrets
import threading
import time

from .agents.base import AgentEvent, AgentSession, ProviderStatus
from .agents.gateway import AgentGateway, AgentGatewayError
from .analysis import InsightResult
from .config import Profile, ProfileError, ProfileStore
from .evidence_context import EvidenceContextBuilder, EvidenceSnapshot, build_source_profile
from .metrics import InputValidationError
from .permissions import OperationRequest, PermissionBroker, PermissionMode
from .sessions import AuditEntry, AuditStore, SessionRecord, SessionStore


BROWSER_SESSION_SECONDS = 600
APPROVAL_SECONDS = 300
MAX_BUFFERED_EVENTS = 256
MAX_EVENT_BYTES = 1_000_000
TERMINAL_EVENTS = {"turn.completed", "turn.cancelled", "turn.error", "provider.error"}


class AgentApiError(ValueError):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


class BrowserSessions:
    def __init__(self, lifetime_seconds: int = BROWSER_SESSION_SECONDS) -> None:
        self.lifetime_seconds = lifetime_seconds
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def issue(self) -> tuple[str, str]:
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        with self._lock:
            self._expire()
            self._tokens[session_id] = (csrf_token, time.monotonic() + self.lifetime_seconds)
        return session_id, csrf_token

    def authorize(self, cookie_header: str | None, csrf_token: str | None = None) -> str:
        session_id = _cookie_value(cookie_header, "d2d2d_session")
        if session_id is None:
            raise AgentApiError(HTTPStatus.FORBIDDEN, "agent request authorization failed")
        with self._lock:
            self._expire()
            expected = self._tokens.get(session_id)
        if expected is None or (csrf_token is not None and not secrets.compare_digest(expected[0], csrf_token)):
            raise AgentApiError(HTTPStatus.FORBIDDEN, "agent request authorization failed")
        return session_id

    def authorize_mutation(self, cookie_header: str | None, csrf_token: str | None) -> str:
        if not csrf_token:
            raise AgentApiError(HTTPStatus.FORBIDDEN, "agent request authorization failed")
        return self.authorize(cookie_header, csrf_token)

    def _expire(self) -> None:
        now = time.monotonic()
        self._tokens = {
            session_id: value
            for session_id, value in self._tokens.items()
            if value[1] > now
        }


class EventBuffer:
    def __init__(self, maximum: int = MAX_BUFFERED_EVENTS) -> None:
        self._events: deque[tuple[int, AgentEvent]] = deque(maxlen=maximum)
        self._next_id = 1
        self._condition = threading.Condition()

    def append(self, event: AgentEvent) -> int:
        with self._condition:
            event_id = self._next_id
            self._next_id += 1
            self._events.append((event_id, event))
            self._condition.notify_all()
        return event_id

    def after(self, event_id: int, timeout: float = 15.0) -> tuple[tuple[int, AgentEvent], ...]:
        with self._condition:
            available = tuple(item for item in self._events if item[0] > event_id)
            if not available:
                self._condition.wait(timeout=timeout)
                available = tuple(item for item in self._events if item[0] > event_id)
            return available


@dataclass
class PendingApproval:
    request: OperationRequest
    expires_at: datetime


def _context_attached_payload(snapshot: EvidenceSnapshot) -> dict[str, object]:
    """Structure the evidence snapshot so the workbench can render the pipeline."""
    payload: dict[str, object] = snapshot.summary.to_dict()
    payload["source"] = snapshot.source.to_dict()
    payload["metrics"] = [asdict(item) for item in snapshot.metrics]
    if snapshot.analysis is not None:
        payload["analysis"] = snapshot.analysis.to_dict()
    return payload


@dataclass
class WebAgentSession:
    owner_id: str
    agent: AgentSession
    permission_mode: PermissionMode
    broker: PermissionBroker
    events: EventBuffer = field(default_factory=EventBuffer)
    approvals: dict[str, PendingApproval] = field(default_factory=dict)
    busy: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class AgentWebService:
    def __init__(
        self,
        gateway: AgentGateway,
        workspace: Path,
        session_store: SessionStore,
        audit_store: AuditStore,
        profile_store: ProfileStore,
        context_builder: EvidenceContextBuilder | None = None,
    ) -> None:
        self.gateway = gateway
        self.workspace = workspace.expanduser().resolve()
        if not self.workspace.is_dir():
            raise ValueError("agent workspace must be an existing directory")
        self.session_store = session_store
        self.audit_store = audit_store
        self.profile_store = profile_store
        self.context_builder = context_builder or EvidenceContextBuilder()
        self.browser_sessions = BrowserSessions()
        self._sessions: dict[str, WebAgentSession] = {}
        self._analyses: dict[str, tuple[str, InsightResult]] = {}
        self._lock = threading.Lock()

    def list_agents(self) -> list[dict[str, object]]:
        agents = []
        for name in self.gateway.provider_names:
            try:
                status = self.gateway.detect(name)
            except AgentGatewayError as error:
                status = ProviderStatus(False, False, detail=_provider_error_message(error))
            agents.append(_status_payload(name, status))
        return agents

    def create_session(self, owner_id: str, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "session request must be an object")
        provider = payload.get("provider")
        permission_mode = payload.get("permission_mode", "collaborative")
        resume_id = payload.get("resume_id")
        if not isinstance(provider, str) or not provider:
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "provider is required")
        if permission_mode not in {"read_only", "collaborative", "trusted_session"}:
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "permission mode is invalid")
        if resume_id is not None and (not isinstance(resume_id, str) or not resume_id):
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "resume ID is invalid")
        try:
            with self._lock:
                self.gateway.connect(provider)
                agent_session = self.gateway.create_session(provider, self.workspace, resume_id)
                web_session = WebAgentSession(
                    owner_id=owner_id,
                    agent=agent_session,
                    permission_mode=permission_mode,
                    broker=PermissionBroker(permission_mode, (self.workspace,)),
                )
                self._sessions[agent_session.id] = web_session
        except AgentGatewayError as error:
            raise AgentApiError(HTTPStatus.CONFLICT, _provider_error_message(error)) from error
        now = datetime.now(timezone.utc).isoformat()
        self.session_store.upsert(
            SessionRecord(
                id=agent_session.id,
                provider=agent_session.provider,
                provider_session_id=agent_session.provider_session_id,
                workspace=str(agent_session.workspace),
                permission_mode=permission_mode,
                created_at=now,
                updated_at=now,
            )
        )
        self._audit(web_session, "session", "agent session created", "allowed")
        return _session_payload(web_session)

    def start_turn(self, owner_id: str, session_id: str, payload: object) -> None:
        web_session = self._session(owner_id, session_id)
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), str):
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "agent message is required")
        message = payload["message"].strip()
        if not message:
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "agent message is required")
        try:
            profile = self.profile_store.load() or Profile.demo()
            with self._lock:
                analysis_fingerprint, analysis = self._analyses.get(owner_id, (None, None))
            snapshot = self.context_builder.build(
                message,
                profile,
                analysis=analysis,
                analysis_source_fingerprint=analysis_fingerprint,
                cache_path=self.profile_store.index_cache_path,
            )
        except (InputValidationError, ProfileError) as error:
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, str(error)) from error
        with web_session.lock:
            if web_session.busy:
                raise AgentApiError(HTTPStatus.CONFLICT, "agent session already has an active turn")
            web_session.busy = True
        web_session.events.append(AgentEvent("context.attached", _context_attached_payload(snapshot)))
        self._audit(
            web_session,
            "context",
            (
                f"snapshot {snapshot.summary.snapshot_id}; records={snapshot.summary.record_count}; "
                f"metrics={snapshot.summary.metric_count}; excerpts={snapshot.summary.excerpt_count}; "
                f"compressed={snapshot.summary.compressed}"
            ),
            "allowed",
        )
        threading.Thread(
            target=self._run_turn,
            args=(web_session, snapshot.render_prompt(message)),
            name=f"agent-turn-{session_id[:8]}",
            daemon=True,
        ).start()

    def record_analysis(self, owner_id: str, result: InsightResult, profile: Profile) -> None:
        source_fingerprint = build_source_profile(profile).fingerprint
        with self._lock:
            self._analyses[owner_id] = (source_fingerprint, result)

    def invalidate_analysis(self) -> None:
        with self._lock:
            self._analyses.clear()

    def event_buffer(self, owner_id: str, session_id: str) -> EventBuffer:
        return self._session(owner_id, session_id).events

    def decide_approval(
        self,
        owner_id: str,
        session_id: str,
        approval_id: str,
        payload: object,
    ) -> None:
        web_session = self._session(owner_id, session_id)
        if not isinstance(payload, dict) or not isinstance(payload.get("approved"), bool):
            raise AgentApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "approval decision must be boolean")
        try:
            pending = web_session.approvals.pop(approval_id)
        except KeyError as error:
            raise AgentApiError(HTTPStatus.NOT_FOUND, "approval request is not pending") from error
        now = datetime.now(timezone.utc)
        if pending.expires_at <= now:
            self._provider_decision(web_session, approval_id, False)
            self._audit(web_session, pending.request.kind, pending.request.summary, "expired")
            raise AgentApiError(HTTPStatus.GONE, "approval request has expired")
        approved = payload["approved"]
        if approved:
            decision = web_session.broker.approve(pending.request, ttl_seconds=APPROVAL_SECONDS)
            if decision.status != "allowed":
                approved = False
        self._provider_decision(web_session, approval_id, approved)
        self._audit(
            web_session,
            pending.request.kind,
            pending.request.summary,
            "approved" if approved else "rejected",
            pending.request.target_paths,
        )

    def interrupt(self, owner_id: str, session_id: str) -> None:
        web_session = self._session(owner_id, session_id)
        try:
            self.gateway.interrupt(web_session.agent.provider, web_session.agent)
        except AgentGatewayError as error:
            raise AgentApiError(HTTPStatus.CONFLICT, _provider_error_message(error)) from error
        self._audit(web_session, "interrupt", "agent turn interrupted", "allowed")

    def close(self) -> None:
        self.gateway.close()

    def _run_turn(self, web_session: WebAgentSession, message: str) -> None:
        try:
            for event in self.gateway.send(web_session.agent.provider, web_session.agent, message):
                routed = self._route_event(web_session, event)
                if routed is not None:
                    _validate_browser_event(routed)
                    web_session.events.append(routed)
        except AgentGatewayError as error:
            web_session.events.append(
                AgentEvent(
                    "turn.error",
                    {"message": _provider_error_message(error), "code": type(error).__name__},
                )
            )
        except AgentApiError as error:
            web_session.events.append(
                AgentEvent("turn.error", {"message": str(error), "code": type(error).__name__})
            )
        except Exception:
            web_session.events.append(
                AgentEvent("turn.error", {"message": "agent turn failed", "code": "AgentTurnFailure"})
            )
        finally:
            with web_session.lock:
                web_session.busy = False

    def _route_event(self, web_session: WebAgentSession, event: AgentEvent) -> AgentEvent | None:
        if event.kind != "approval.request":
            return event
        try:
            request, expires_at = _operation_request(web_session, event.payload)
        except ValueError:
            request_id = str(event.payload.get("request_id", ""))
            if request_id:
                self._provider_decision(web_session, request_id, False)
            return AgentEvent(
                "tool.result",
                {"call_id": request_id or "invalid-approval", "result": "operation request was rejected", "error": True},
            )
        decision = web_session.broker.evaluate(request)
        if decision.status == "rejected":
            self._provider_decision(web_session, request.request_id, False)
            self._audit(web_session, request.kind, request.summary, "blocked", request.target_paths)
            return AgentEvent(
                "tool.result",
                {"call_id": request.request_id, "result": decision.reason, "error": True},
            )
        if decision.status == "allowed":
            self._provider_decision(web_session, request.request_id, True)
            self._audit(web_session, request.kind, request.summary, "approved", request.target_paths)
            return None
        web_session.approvals[request.request_id] = PendingApproval(request, expires_at)
        payload = dict(event.payload)
        payload["expires_at"] = expires_at.isoformat()
        return AgentEvent("approval.request", payload)

    def _provider_decision(self, web_session: WebAgentSession, approval_id: str, approved: bool) -> None:
        try:
            self.gateway.decide_approval(
                web_session.agent.provider,
                web_session.agent,
                approval_id,
                approved,
            )
        except AgentGatewayError as error:
            raise AgentApiError(HTTPStatus.CONFLICT, _provider_error_message(error)) from error

    def _session(self, owner_id: str, session_id: str) -> WebAgentSession:
        web_session = self._sessions.get(session_id)
        if web_session is None or not secrets.compare_digest(web_session.owner_id, owner_id):
            raise AgentApiError(HTTPStatus.NOT_FOUND, "agent session was not found")
        return web_session

    def _audit(
        self,
        web_session: WebAgentSession,
        operation: str,
        summary: str,
        decision: str,
        target_paths: tuple[Path, ...] = (),
    ) -> None:
        self.audit_store.append(
            AuditEntry(
                timestamp=datetime.now(timezone.utc),
                provider=web_session.agent.provider,
                session_id=web_session.agent.id,
                operation=operation,
                summary=summary,
                decision=decision,
                target_paths=tuple(str(path) for path in target_paths),
            )
        )


def _operation_request(
    web_session: WebAgentSession,
    payload: dict[str, object],
) -> tuple[OperationRequest, datetime]:
    request_id = payload.get("request_id")
    operation = payload.get("operation")
    if not isinstance(request_id, str) or not request_id or not isinstance(operation, str):
        raise ValueError("invalid approval request")
    kind = operation if operation in {"read", "write", "command"} else "tool"
    working_directory = payload.get("working_directory") or str(web_session.agent.workspace)
    target_paths = payload.get("target_paths", [])
    command = payload.get("command")
    if not isinstance(working_directory, str):
        raise ValueError("invalid working directory")
    if not isinstance(target_paths, list) or not all(isinstance(path, str) for path in target_paths):
        raise ValueError("invalid target paths")
    if command is not None and not isinstance(command, str):
        raise ValueError("invalid command")
    expires_at = _approval_expiry(payload.get("expires_at"))
    request = OperationRequest(
        provider=web_session.agent.provider,
        session_id=web_session.agent.id,
        kind=kind,
        working_directory=Path(working_directory),
        target_paths=tuple(Path(path) for path in target_paths),
        command=command if kind == "command" else None,
        tool_name=operation if kind == "tool" else None,
        summary=command or operation,
        request_id=request_id,
    )
    return request, expires_at


def _approval_expiry(value: object) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed
    return datetime.now(timezone.utc) + timedelta(seconds=APPROVAL_SECONDS)


def _status_payload(name: str, status: ProviderStatus) -> dict[str, object]:
    return {
        "name": name,
        "available": status.available,
        "connected": status.connected,
        "version": status.version[:200] if isinstance(status.version, str) else None,
        "authenticated": status.authenticated,
        "compatible": status.compatible,
        "detail": _safe_status_detail(status),
    }


def _session_payload(web_session: WebAgentSession) -> dict[str, object]:
    return {
        "id": web_session.agent.id,
        "provider": web_session.agent.provider,
        "workspace": str(web_session.agent.workspace),
        "permission_mode": web_session.permission_mode,
        "resumed": web_session.agent.resumed,
    }


def _provider_error_message(error: AgentGatewayError) -> str:
    names = {
        "NotInstalled": "provider is not installed",
        "NotAuthenticated": "provider is not authenticated",
        "IncompatibleVersion": "provider version is incompatible",
        "ProviderTimeout": "provider request timed out",
        "InvalidProviderPayload": "provider returned an invalid response",
    }
    return names.get(type(error).__name__, "provider is unavailable")


def _safe_status_detail(status: ProviderStatus) -> str | None:
    if not status.available:
        return "provider is not installed or unavailable"
    if not status.authenticated:
        return "provider is not authenticated"
    if not status.compatible:
        return "provider version is incompatible"
    return None


def _validate_browser_event(event: AgentEvent) -> None:
    try:
        encoded = json.dumps(
            {"kind": event.kind, "payload": event.payload},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise AgentApiError(HTTPStatus.BAD_GATEWAY, "provider returned an invalid event") from error
    if len(encoded) > MAX_EVENT_BYTES:
        raise AgentApiError(HTTPStatus.BAD_GATEWAY, "provider event is too large")


def _cookie_value(cookie_header: str | None, name: str) -> str | None:
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except CookieError:
        return None
    morsel = cookie.get(name)
    return morsel.value if morsel is not None else None
