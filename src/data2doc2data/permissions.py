"""Session-scoped permission decisions for local agent operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shlex
from typing import Callable, Literal
import uuid


PermissionMode = Literal["read_only", "collaborative", "trusted_session"]
OperationKind = Literal["read", "write", "command", "tool"]
DecisionStatus = Literal["allowed", "pending", "rejected"]


@dataclass(frozen=True)
class OperationRequest:
    provider: str
    session_id: str
    kind: OperationKind
    working_directory: Path
    target_paths: tuple[Path, ...] = ()
    command: str | None = None
    tool_name: str | None = None
    summary: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if not self.provider or not self.session_id or not self.request_id:
            raise ValueError("operation provider, session, and request IDs are required")
        if self.kind not in {"read", "write", "command", "tool"}:
            raise ValueError("unsupported operation kind")
        if not isinstance(self.working_directory, Path):
            raise ValueError("working directory must be a path")
        if self.kind == "command" and not self.command:
            raise ValueError("command operation requires a command")
        if self.kind == "tool" and not self.tool_name:
            raise ValueError("tool operation requires a tool name")


@dataclass(frozen=True)
class PermissionDecision:
    status: DecisionStatus
    reason: str
    request_id: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class _Grant:
    provider: str
    session_id: str
    kind: OperationKind
    root: Path
    command_prefix: tuple[str, ...]
    tool_name: str | None
    expires_at: datetime


class PermissionBroker:
    def __init__(
        self,
        mode: PermissionMode,
        roots: tuple[Path, ...],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if mode not in {"read_only", "collaborative", "trusted_session"}:
            raise ValueError("unsupported permission mode")
        if not roots:
            raise ValueError("at least one workspace root is required")
        resolved_roots = tuple(sorted({root.expanduser().resolve() for root in roots}, key=str))
        if any(not root.is_dir() for root in resolved_roots):
            raise ValueError("workspace roots must be existing directories")
        self.mode = mode
        self.roots = resolved_roots
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._grants: list[_Grant] = []
        self._one_time_approvals: dict[tuple[object, ...], datetime] = {}

    def evaluate(self, request: OperationRequest) -> PermissionDecision:
        root = self._scope_root(request)
        if root is None:
            return PermissionDecision("rejected", "operation target is outside approved roots", request.request_id)
        if request.kind == "read":
            return PermissionDecision("allowed", "read is within an approved root", request.request_id)
        if self.mode == "read_only":
            return PermissionDecision("rejected", "read-only mode blocks state changes", request.request_id)

        now = self._now()
        self._expire(now)
        fingerprint = self._fingerprint(request, root)
        one_time_expiry = self._one_time_approvals.pop(fingerprint, None)
        if one_time_expiry is not None and one_time_expiry > now:
            return PermissionDecision("allowed", "operation has a one-time approval", request.request_id, one_time_expiry)
        for grant in self._grants:
            if self._matches(grant, request, root):
                return PermissionDecision("allowed", "operation matches a trusted session grant", request.request_id, grant.expires_at)
        return PermissionDecision("pending", "operation requires user approval", request.request_id)

    def approve(
        self,
        request: OperationRequest,
        ttl_seconds: int = 300,
        command_prefix: str | None = None,
    ) -> PermissionDecision:
        root = self._scope_root(request)
        if root is None:
            return PermissionDecision("rejected", "operation target is outside approved roots", request.request_id)
        if request.kind == "read":
            return PermissionDecision("allowed", "read is already allowed", request.request_id)
        if self.mode == "read_only":
            return PermissionDecision("rejected", "read-only mode blocks approvals", request.request_id)
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("approval lifetime must be a positive number of seconds")
        expires_at = self._now() + timedelta(seconds=ttl_seconds)
        if self.mode == "collaborative":
            self._one_time_approvals[self._fingerprint(request, root)] = expires_at
        else:
            prefix = self._command_tokens(command_prefix if command_prefix is not None else request.command)
            requested_command = self._command_tokens(request.command)
            if request.kind == "command" and requested_command[: len(prefix)] != prefix:
                raise ValueError("command grant prefix must match the approved request")
            self._grants.append(
                _Grant(
                    provider=request.provider,
                    session_id=request.session_id,
                    kind=request.kind,
                    root=root,
                    command_prefix=prefix,
                    tool_name=request.tool_name,
                    expires_at=expires_at,
                )
            )
        return PermissionDecision("allowed", "operation was approved", request.request_id, expires_at)

    def revoke_session(self, provider: str, session_id: str) -> None:
        self._grants = [
            grant
            for grant in self._grants
            if (grant.provider, grant.session_id) != (provider, session_id)
        ]
        self._one_time_approvals = {
            fingerprint: expiry
            for fingerprint, expiry in self._one_time_approvals.items()
            if fingerprint[:2] != (provider, session_id)
        }

    def _scope_root(self, request: OperationRequest) -> Path | None:
        working_directory = request.working_directory.expanduser().resolve()
        targets = tuple(
            (path if path.is_absolute() else working_directory / path).expanduser().resolve()
            for path in request.target_paths
        )
        for root in sorted(self.roots, key=lambda candidate: len(candidate.parts), reverse=True):
            if self._inside(working_directory, root) and all(self._inside(path, root) for path in targets):
                return root
        return None

    def _matches(self, grant: _Grant, request: OperationRequest, root: Path) -> bool:
        if (
            grant.provider != request.provider
            or grant.session_id != request.session_id
            or grant.kind != request.kind
            or grant.root != root
            or grant.tool_name != request.tool_name
        ):
            return False
        if request.kind != "command":
            return True
        command = self._command_tokens(request.command)
        return bool(grant.command_prefix) and command[: len(grant.command_prefix)] == grant.command_prefix

    def _expire(self, now: datetime) -> None:
        self._grants = [grant for grant in self._grants if grant.expires_at > now]
        self._one_time_approvals = {
            fingerprint: expiry
            for fingerprint, expiry in self._one_time_approvals.items()
            if expiry > now
        }

    def _now(self) -> datetime:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("permission clock must return a timezone-aware datetime")
        return now

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        return path == root or root in path.parents

    @staticmethod
    def _command_tokens(command: str | None) -> tuple[str, ...]:
        if not command:
            return ()
        try:
            return tuple(shlex.split(command))
        except ValueError as error:
            raise ValueError("command has invalid shell quoting") from error

    def _fingerprint(self, request: OperationRequest, root: Path) -> tuple[object, ...]:
        working_directory = request.working_directory.expanduser().resolve()
        targets = tuple(
            str((path if path.is_absolute() else working_directory / path).expanduser().resolve())
            for path in request.target_paths
        )
        return (
            request.provider,
            request.session_id,
            request.request_id,
            request.kind,
            str(root),
            str(working_directory),
            targets,
            self._command_tokens(request.command),
            request.tool_name,
        )
