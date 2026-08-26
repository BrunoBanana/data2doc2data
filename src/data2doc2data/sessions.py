"""Private local session metadata and redacted append-only audit storage."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import threading


SESSION_STORE_VERSION = 1
REDACTION_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s'\"]+"), r"\1[REDACTED]"),
    (
        re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)[^\s,'\"]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
)


class SessionStoreError(ValueError):
    pass


@dataclass(frozen=True)
class AuditEntry:
    timestamp: datetime
    provider: str
    session_id: str
    operation: str
    summary: str
    decision: str
    exit_status: int | None = None
    target_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionRecord:
    id: str
    provider: str
    provider_session_id: str
    workspace: str
    permission_mode: str
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        text_fields = (
            self.id,
            self.provider,
            self.provider_session_id,
            self.workspace,
            self.permission_mode,
            self.created_at,
            self.updated_at,
        )
        if any(not isinstance(value, str) for value in text_fields):
            raise SessionStoreError("session fields must be text")
        if not self.id or not self.provider or not self.provider_session_id or not self.workspace:
            raise SessionStoreError("session identifiers and workspace are required")
        if self.permission_mode not in {"read_only", "collaborative", "trusted_session"}:
            raise SessionStoreError("invalid session permission mode")
        try:
            created_at = datetime.fromisoformat(self.created_at)
            updated_at = datetime.fromisoformat(self.updated_at)
        except ValueError as error:
            raise SessionStoreError("session timestamps must be ISO-8601") from error
        if created_at.tzinfo is None or updated_at.tzinfo is None:
            raise SessionStoreError("session timestamps must include a timezone")


class AuditStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._lock = threading.Lock()

    def append(self, entry: AuditEntry) -> None:
        if entry.timestamp.tzinfo is None:
            raise ValueError("audit timestamp must include a timezone")
        payload = {
            "timestamp": entry.timestamp.isoformat(),
            "provider": _redact(entry.provider),
            "session_id": _redact(entry.session_id),
            "operation": _redact(entry.operation),
            "summary": _redact(entry.summary[:10_000]),
            "decision": _redact(entry.decision),
            "exit_status": entry.exit_status,
            "target_paths": [_redact(path) for path in entry.target_paths[:100]],
        }
        line = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.chmod(self.path, 0o600)
                written = 0
                while written < len(line):
                    written += os.write(descriptor, line[written:])
            finally:
                os.close(descriptor)


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self._lock = threading.Lock()

    def get(self, session_id: str) -> SessionRecord | None:
        return {record.id: record for record in self.list()}.get(session_id)

    def list(self) -> tuple[SessionRecord, ...]:
        with self._lock:
            records = self._load()
        return tuple(sorted(records.values(), key=lambda record: record.id))

    def upsert(self, record: SessionRecord) -> SessionRecord:
        with self._lock:
            records = self._load()
            records[record.id] = record
            self._write(records)
        return record

    def delete(self, session_id: str) -> bool:
        with self._lock:
            records = self._load()
            removed = records.pop(session_id, None) is not None
            if removed:
                self._write(records)
        return removed

    def _load(self) -> dict[str, SessionRecord]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("version") != SESSION_STORE_VERSION:
                raise SessionStoreError("unsupported session store format")
            raw_records = payload.get("sessions")
            if not isinstance(raw_records, list):
                raise SessionStoreError("session store must contain a session list")
            records = {}
            for raw in raw_records:
                if not isinstance(raw, dict):
                    raise SessionStoreError("session record must be an object")
                record = SessionRecord(
                    id=raw["id"],
                    provider=raw["provider"],
                    provider_session_id=raw["provider_session_id"],
                    workspace=raw["workspace"],
                    permission_mode=raw["permission_mode"],
                    created_at=raw["created_at"],
                    updated_at=raw["updated_at"],
                )
                if record.id in records:
                    raise SessionStoreError("duplicate session ID")
                records[record.id] = record
            return records
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, SessionStoreError) as error:
            if isinstance(error, SessionStoreError) and str(error).startswith("cannot read"):
                raise
            raise SessionStoreError(f"cannot read session store: {error}") from error

    def _write(self, records: dict[str, SessionRecord]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        payload = {
            "version": SESSION_STORE_VERSION,
            "sessions": [asdict(records[key]) for key in sorted(records)],
        }
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
            os.chmod(temporary_path, 0o600)
            temporary_path.replace(self.path)
        except OSError as error:
            raise SessionStoreError(f"cannot write session store: {error}") from error
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()


def _redact(value: str) -> str:
    redacted = value
    for pattern, replacement in REDACTION_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted
