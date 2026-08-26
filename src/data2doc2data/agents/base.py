"""Provider-neutral agent protocol types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Protocol


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    connected: bool
    version: str | None = None
    authenticated: bool = True
    compatible: bool = True
    detail: str | None = None


@dataclass(frozen=True)
class AgentSession:
    id: str
    provider: str
    provider_session_id: str
    workspace: Path
    resumed: bool = False


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    operation: str
    command: str | None = None
    working_directory: str | None = None
    target_paths: tuple[str, ...] = ()
    diff: str | None = None
    expires_at: str | None = None


class AgentProvider(Protocol):
    name: str

    def detect(self) -> ProviderStatus: ...

    def connect(self) -> None: ...

    def create_session(self, workspace: Path, resume_id: str | None = None) -> AgentSession | str: ...

    def stream_turn(
        self,
        session: AgentSession,
        message: str,
    ) -> Iterable[AgentEvent | Mapping[str, object]]: ...

    def decide_approval(
        self,
        session: AgentSession,
        approval_id: str,
        approved: bool,
    ) -> None: ...

    def interrupt(self, session: AgentSession) -> None: ...

    def close(self) -> None: ...
