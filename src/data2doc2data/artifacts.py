"""Immutable local storage for full analytical artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Mapping

from .diagnostics import AnalyticalArtifact


_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


class ArtifactStore:
    """Persist full artifacts locally while exposing only opaque IDs upstream."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def save(self, artifact_id: str, kind: str, payload: Mapping[str, object]) -> str:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("artifact ID is invalid")
        if not kind or len(kind) > 80:
            raise ValueError("artifact kind is invalid")
        record = {"artifact_id": artifact_id, "kind": kind, "payload": _json_value(payload)}
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        target = self.root / f"{artifact_id}.json"
        if target.exists():
            if target.read_bytes() != encoded:
                raise ValueError("artifacts are immutable")
            return artifact_id
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise ValueError("artifacts are immutable") from None
            return artifact_id
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        return artifact_id

    def save_analytical(self, artifact: AnalyticalArtifact) -> str:
        return self.save(artifact.artifact_id, "analytical", analytical_artifact_payload(artifact))

    def load(self, artifact_id: str) -> dict[str, object]:
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError("artifact ID is invalid")
        target = self.root / f"{artifact_id}.json"
        try:
            value = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("artifact is unavailable") from exc
        if not isinstance(value, dict) or value.get("artifact_id") != artifact_id:
            raise ValueError("artifact record is invalid")
        return value

    def load_analytical(self, artifact_id: str) -> AnalyticalArtifact:
        record = self.load(artifact_id)
        if record.get("kind") != "analytical" or not isinstance(record.get("payload"), dict):
            raise ValueError("artifact is not analytical")
        payload = record["payload"]
        return AnalyticalArtifact(
            str(payload["artifact_id"]),
            str(payload["method"]),
            str(payload["status"]),
            str(payload["summary"]),
            dict(payload["observations"]),
            int(payload["sample_size"]),
            dict(payload["parameters"]),
            tuple(dict(item) for item in payload.get("diagnostics", [])),
            tuple(str(item) for item in payload.get("limitations", [])),
            tuple(str(item) for item in payload.get("source_refs", [])),
        )


def analytical_artifact_payload(artifact: AnalyticalArtifact) -> dict[str, object]:
    return {
        "artifact_id": artifact.artifact_id,
        "method": artifact.method,
        "status": artifact.status,
        "summary": artifact.summary,
        "observations": _json_value(artifact.observations),
        "sample_size": artifact.sample_size,
        "parameters": _json_value(artifact.parameters),
        "diagnostics": [_json_value(item) for item in artifact.diagnostics],
        "limitations": list(artifact.limitations),
        "source_refs": list(artifact.source_refs),
    }


def _json_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"artifact payload contains unsupported value: {type(value).__name__}")
