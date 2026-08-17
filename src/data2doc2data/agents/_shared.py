"""Shared, provider-neutral helpers for local agent adapters.

Codex and WorkBuddy speak different wire protocols (newline-delimited JSON-RPC
on stdio versus ACP-over-SSE), but they share the same lifecycle concerns:
emitting a provider-level error to every active session queue and validating
that a session belongs to the adapter's approved workspace. These helpers keep
that behavior in one place.
"""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path
from queue import Queue

from .base import AgentEvent, AgentSession
from .gateway import InvalidProviderPayload


def emit_provider_error(
    event_queues: Mapping[str, "Queue[AgentEvent]"],
    message: str,
    code: str,
) -> None:
    """Broadcast a provider-level error to every active session queue."""
    event = AgentEvent("provider.error", {"message": message, "code": code})
    for event_queue in tuple(event_queues.values()):
        event_queue.put(event)


def validate_session(
    provider_name: str,
    session: AgentSession,
    workspace: Path,
    event_queues: Mapping[str, "Queue[AgentEvent]"],
) -> None:
    """Reject a session that does not belong to this adapter's approved workspace."""
    if session.provider != provider_name or session.workspace.resolve() != workspace:
        raise ValueError(f"{provider_name} session does not match this provider workspace")
    if session.provider_session_id not in event_queues:
        raise ValueError(f"{provider_name} session is not active")


def minimal_environment(*extra: str) -> dict[str, str]:
    """Return a minimal child-process environment, never inheriting secrets."""
    allowed = ("PATH", "HOME", "USER", "TMPDIR", "LANG", "LC_ALL", "SHELL", *extra)
    return {key: os.environ[key] for key in allowed if key in os.environ}


def required_text(
    provider_name: str,
    value: Mapping[str, object],
    key: str,
    nonempty: bool = False,
) -> str:
    """Extract a required string field from a provider payload."""
    result = value.get(key)
    if not isinstance(result, str) or (nonempty and not result):
        raise InvalidProviderPayload(provider_name, f"{provider_name} field '{key}' must be text")
    return result
