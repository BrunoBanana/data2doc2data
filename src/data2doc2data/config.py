"""Persist local workspace choices without storing credentials."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from typing import Literal

from .demo_scenarios import DEFAULT_DEMO_SCENARIO, DemoScenarioCatalog, DemoScenarioError


ProfileMode = Literal["demo", "local", "api"]


class ProfileError(ValueError):
    """Raised when a saved workspace profile cannot be read safely."""


@dataclass(frozen=True)
class Profile:
    mode: ProfileMode
    data_path: str
    knowledge_path: str
    demo_scenario: str = DEFAULT_DEMO_SCENARIO
    rules_path: str = ""
    ingestion: dict | None = None
    api: dict | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"demo", "local", "api"}:
            raise ProfileError("mode must be 'demo', 'local' or 'api'")
        if not isinstance(self.data_path, str) or not isinstance(self.knowledge_path, str):
            raise ProfileError("source paths must be text")
        if not isinstance(self.demo_scenario, str):
            raise ProfileError("demo scenario must be text")
        if not isinstance(self.rules_path, str):
            raise ProfileError("rules path must be text")
        for name in ("ingestion", "api"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, dict):
                raise ProfileError(f"{name} config must be a JSON object")
        if self.mode == "demo":
            try:
                DemoScenarioCatalog.load().get(self.demo_scenario)
            except DemoScenarioError as error:
                raise ProfileError(str(error)) from error

    @classmethod
    def demo(cls, scenario_id: str = DEFAULT_DEMO_SCENARIO) -> "Profile":
        return cls(mode="demo", data_path="", knowledge_path="", demo_scenario=scenario_id)

    def to_dict(self) -> dict[str, object]:
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
                demo_scenario=value.get("demo_scenario", DEFAULT_DEMO_SCENARIO),
                rules_path=value.get("rules_path", ""),
                ingestion=value.get("ingestion"),
                api=value.get("api"),
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

    @property
    def workspace_database_path(self) -> Path:
        """Keep new task metadata beside, but separate from, the legacy profile JSON."""
        return self.path.parent / "workbench.sqlite3"

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
