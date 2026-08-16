"""Persist local workspace choices without storing credentials."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Literal


ProfileMode = Literal["demo", "local"]


class ProfileError(ValueError):
    """Raised when a saved workspace profile cannot be read safely."""


@dataclass(frozen=True)
class Profile:
    mode: ProfileMode
    data_path: str
    knowledge_path: str

    def __post_init__(self) -> None:
        if self.mode not in {"demo", "local"}:
            raise ProfileError("mode must be 'demo' or 'local'")
        if not isinstance(self.data_path, str) or not isinstance(self.knowledge_path, str):
            raise ProfileError("source paths must be text")

    @classmethod
    def demo(cls) -> "Profile":
        return cls(mode="demo", data_path="", knowledge_path="")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: object) -> "Profile":
        if not isinstance(value, dict):
            raise ProfileError("profile must be a JSON object")
        try:
            return cls(
                mode=value["mode"],
                data_path=value.get("data_path", ""),
                knowledge_path=value.get("knowledge_path", ""),
            )
        except (KeyError, TypeError) as error:
            raise ProfileError("profile is missing required fields") from error


class ProfileStore:
    """Store only user-selected source paths in a local JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    @property
    def index_cache_path(self) -> Path:
        return self.path.parent / "document-index.json"

    def load(self) -> Profile | None:
        if not self.path.is_file():
            return None
        try:
            return Profile.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ProfileError) as error:
            raise ProfileError(f"cannot read profile: {error}") from error

    def save(self, profile: Profile) -> Profile:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(self.path)
        return profile


def default_store() -> ProfileStore:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    return ProfileStore(config_home / "data2doc2data" / "config.json")
