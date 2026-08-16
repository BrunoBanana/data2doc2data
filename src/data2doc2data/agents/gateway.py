"""Lifecycle and event normalization for local agent providers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
import uuid

from .base import AgentEvent, AgentProvider, AgentSession, ProviderStatus


class AgentGatewayError(RuntimeError):
    def __init__(self, provider: str, message: str) -> None:
        super().__init__(message)
        self.provider = provider


class NotInstalled(AgentGatewayError):
    pass


class NotAuthenticated(AgentGatewayError):
    pass


class IncompatibleVersion(AgentGatewayError):
    pass


class ProviderUnavailable(AgentGatewayError):
    pass


class ProviderTimeout(AgentGatewayError):
    pass


class InvalidProviderPayload(AgentGatewayError):
    pass


EVENT_FIELDS = {
    "session.started": ({"session_id"}, {"session_id"}),
    "message.delta": ({"text"}, {"text"}),
    "plan.delta": ({"text"}, {"text"}),
    "command.output": ({"text", "stream", "command_id"}, {"text"}),
    "file.diff": ({"path", "diff"}, {"path", "diff"}),
    "tool.call": ({"call_id", "name", "arguments"}, {"call_id", "name"}),
    "tool.result": ({"call_id", "result", "error"}, {"call_id"}),
    "approval.request": (
        {"request_id", "operation", "command", "working_directory", "target_paths", "diff", "expires_at"},
        {"request_id", "operation"},
    ),
    "turn.completed": ({"turn_id", "usage", "reason"}, set()),
    "turn.cancelled": ({"turn_id", "reason"}, set()),
    "turn.error": ({"turn_id", "message", "code"}, {"message"}),
    "provider.error": ({"message", "code"}, {"message"}),
}
STRING_FIELDS = {
    "session_id",
    "text",
    "stream",
    "command_id",
    "path",
    "diff",
    "call_id",
    "name",
    "request_id",
    "operation",
    "command",
    "working_directory",
    "expires_at",
    "turn_id",
    "reason",
    "message",
    "code",
}


class AgentGateway:
    def __init__(self, providers: Mapping[str, AgentProvider]) -> None:
        self._providers = dict(providers)
        if any(name != provider.name for name, provider in self._providers.items()):
            raise ValueError("provider registry keys must match provider names")
        self._connected: set[str] = set()
        self._sessions: dict[str, AgentSession] = {}

    def detect(self, provider_name: str) -> ProviderStatus:
        provider = self._provider(provider_name)
        try:
            status = provider.detect()
        except TimeoutError as error:
            raise ProviderTimeout(provider_name, "provider detection timed out") from error
        except AgentGatewayError:
            raise
        except Exception as error:
            raise ProviderUnavailable(provider_name, "provider detection failed") from error
        if not isinstance(status, ProviderStatus):
            raise InvalidProviderPayload(provider_name, "provider returned an invalid status")
        return status

    def detect_all(self) -> dict[str, ProviderStatus]:
        return {name: self.detect(name) for name in sorted(self._providers)}

    def connect(self, provider_name: str) -> ProviderStatus:
        provider = self._provider(provider_name)
        status = self.detect(provider_name)
        if not status.available:
            raise NotInstalled(provider_name, f"provider '{provider_name}' is not installed")
        if not status.authenticated:
            raise NotAuthenticated(provider_name, f"provider '{provider_name}' is not authenticated")
        if not status.compatible:
            raise IncompatibleVersion(provider_name, f"provider '{provider_name}' has an incompatible version")
        try:
            provider.connect()
        except TimeoutError as error:
            raise ProviderTimeout(provider_name, "provider connection timed out") from error
        except AgentGatewayError:
            raise
        except Exception as error:
            raise ProviderUnavailable(provider_name, "provider connection failed") from error
        self._connected.add(provider_name)
        connected_status = self.detect(provider_name)
        if not connected_status.connected:
            raise ProviderUnavailable(provider_name, "provider did not report a connected state")
        return connected_status

    def create_session(
        self,
        provider_name: str,
        workspace: Path,
        resume_id: str | None = None,
    ) -> AgentSession:
        provider = self._connected_provider(provider_name)
        resolved_workspace = workspace.expanduser().resolve()
        if not resolved_workspace.is_dir():
            raise ValueError("agent workspace must be an existing directory")
        try:
            created = provider.create_session(resolved_workspace, resume_id)
        except TimeoutError as error:
            raise ProviderTimeout(provider_name, "session creation timed out") from error
        except AgentGatewayError:
            raise
        except Exception as error:
            raise ProviderUnavailable(provider_name, "session creation failed") from error
        if isinstance(created, AgentSession):
            valid_workspace = (
                isinstance(created.workspace, Path)
                and created.workspace.expanduser().resolve() == resolved_workspace
            )
            if (
                created.provider != provider_name
                or not created.id
                or not created.provider_session_id
                or not valid_workspace
                or created.id in self._sessions
            ):
                raise InvalidProviderPayload(provider_name, "provider returned an invalid session")
            session = created
        elif isinstance(created, str) and created:
            session = AgentSession(
                id=uuid.uuid4().hex,
                provider=provider_name,
                provider_session_id=created,
                workspace=resolved_workspace,
                resumed=resume_id is not None,
            )
        else:
            raise InvalidProviderPayload(provider_name, "provider returned an invalid session")
        self._sessions[session.id] = session
        return session

    def send(
        self,
        provider_name: str,
        session: AgentSession,
        message: str,
    ) -> Iterator[AgentEvent]:
        provider = self._session_provider(provider_name, session)
        if not isinstance(message, str) or not message.strip():
            raise ValueError("agent message is required")
        try:
            for raw_event in provider.stream_turn(session, message):
                yield self._normalize_event(provider_name, raw_event)
        except TimeoutError as error:
            raise ProviderTimeout(provider_name, "provider turn timed out") from error
        except AgentGatewayError:
            raise
        except Exception as error:
            raise ProviderUnavailable(provider_name, "provider turn failed") from error

    def decide_approval(
        self,
        provider_name: str,
        session: AgentSession,
        approval_id: str,
        approved: bool,
    ) -> None:
        provider = self._session_provider(provider_name, session)
        if not approval_id:
            raise ValueError("approval ID is required")
        if not isinstance(approved, bool):
            raise ValueError("approval decision must be boolean")
        self._call_provider(
            provider_name,
            "approval decision",
            provider.decide_approval,
            session,
            approval_id,
            approved,
        )

    def interrupt(self, provider_name: str, session: AgentSession) -> None:
        provider = self._session_provider(provider_name, session)
        self._call_provider(provider_name, "interruption", provider.interrupt, session)

    def close(self) -> None:
        first_failure = None
        for name, provider in self._providers.items():
            try:
                provider.close()
            except Exception as error:
                first_failure = first_failure or (name, error)
        self._sessions.clear()
        self._connected.clear()
        if first_failure:
            name, error = first_failure
            raise ProviderUnavailable(name, "provider cleanup failed") from error

    def _provider(self, provider_name: str) -> AgentProvider:
        try:
            return self._providers[provider_name]
        except KeyError as error:
            raise NotInstalled(provider_name, f"unknown provider: {provider_name}") from error

    def _connected_provider(self, provider_name: str) -> AgentProvider:
        provider = self._provider(provider_name)
        if provider_name not in self._connected:
            raise ProviderUnavailable(provider_name, "provider is not connected")
        return provider

    def _session_provider(self, provider_name: str, session: AgentSession) -> AgentProvider:
        provider = self._connected_provider(provider_name)
        if session.provider != provider_name or self._sessions.get(session.id) != session:
            raise ProviderUnavailable(provider_name, "agent session is not active")
        return provider

    @staticmethod
    def _call_provider(provider_name: str, action: str, callback, *args) -> None:
        try:
            callback(*args)
        except TimeoutError as error:
            raise ProviderTimeout(provider_name, f"provider {action} timed out") from error
        except AgentGatewayError:
            raise
        except Exception as error:
            raise ProviderUnavailable(provider_name, f"provider {action} failed") from error

    @staticmethod
    def _normalize_event(
        provider_name: str,
        raw_event: AgentEvent | Mapping[str, object],
    ) -> AgentEvent:
        if isinstance(raw_event, AgentEvent):
            kind = raw_event.kind
            payload = raw_event.payload
        elif isinstance(raw_event, Mapping):
            kind = raw_event.get("kind")
            payload = raw_event.get("payload", {})
        else:
            raise InvalidProviderPayload(provider_name, "provider event must be an object")
        if not isinstance(kind, str) or kind not in EVENT_FIELDS:
            raise InvalidProviderPayload(provider_name, "provider event kind is invalid")
        if not isinstance(payload, Mapping):
            raise InvalidProviderPayload(provider_name, "provider event payload must be an object")
        allowed, required = EVENT_FIELDS[kind]
        normalized = {key: payload[key] for key in allowed if key in payload}
        missing = required.difference(normalized)
        if missing:
            raise InvalidProviderPayload(
                provider_name,
                f"provider event is missing required fields: {', '.join(sorted(missing))}",
            )
        for key, value in normalized.items():
            if key in STRING_FIELDS and value is not None and not isinstance(value, str):
                raise InvalidProviderPayload(provider_name, f"provider event field '{key}' must be text")
        return AgentEvent(kind, normalized)
