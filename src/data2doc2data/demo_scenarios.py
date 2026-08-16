"""Validated metadata and fixed paths for built-in synthetic demo scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


DEFAULT_DEMO_SCENARIO = "growth-quality-alert"
CATALOG_VERSION = 1
SCENARIO_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
SCENARIO_FIELDS = frozenset(
    {
        "id",
        "label",
        "summary",
        "suggested_question",
        "learning_objective",
        "expected_validation",
    }
)
VALIDATION_STATES = frozenset({"supported", "contradicted", "mixed", "insufficient"})


class DemoScenarioError(ValueError):
    pass


@dataclass(frozen=True)
class DemoScenario:
    id: str
    label: str
    summary: str
    suggested_question: str
    learning_objective: str
    expected_validation: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class DemoScenarioCatalog:
    def __init__(self, root: Path, scenarios: tuple[DemoScenario, ...], default_id: str) -> None:
        self.root = root.expanduser().resolve()
        self._scenarios = scenarios
        self._by_id = {scenario.id: scenario for scenario in scenarios}
        self._default_id = default_id

    @classmethod
    def load(cls, root: Path | None = None) -> DemoScenarioCatalog:
        catalog_root = (
            root.expanduser().resolve()
            if root is not None
            else Path(__file__).resolve().parent / "sample" / "scenarios"
        )
        try:
            payload = json.loads((catalog_root / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DemoScenarioError("cannot read the demo scenario catalog") from error
        if not isinstance(payload, dict) or set(payload) != {"version", "default", "scenarios"}:
            raise DemoScenarioError("demo scenario catalog fields are invalid")
        if type(payload["version"]) is not int or payload["version"] != CATALOG_VERSION:
            raise DemoScenarioError("unsupported demo scenario catalog version")
        raw_scenarios = payload["scenarios"]
        if not isinstance(raw_scenarios, list) or not raw_scenarios:
            raise DemoScenarioError("demo scenario catalog must contain scenarios")
        scenarios = tuple(_parse_scenario(raw) for raw in raw_scenarios)
        scenario_ids = [scenario.id for scenario in scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise DemoScenarioError("demo scenario catalog contains a duplicate ID")
        default_id = payload["default"]
        if not isinstance(default_id, str) or default_id not in set(scenario_ids):
            raise DemoScenarioError("demo scenario catalog default is unknown")
        return cls(catalog_root, scenarios, default_id)

    @property
    def default(self) -> DemoScenario:
        return self._by_id[self._default_id]

    def list(self) -> tuple[DemoScenario, ...]:
        return self._scenarios

    def get(self, scenario_id: str) -> DemoScenario:
        if not isinstance(scenario_id, str) or SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None:
            raise DemoScenarioError("invalid demo scenario ID")
        try:
            return self._by_id[scenario_id]
        except KeyError as error:
            raise DemoScenarioError("unknown demo scenario ID") from error

    def sources(self, scenario_id: str) -> tuple[Path, Path]:
        scenario = self.get(scenario_id)
        scenario_root = (self.root / scenario.id).resolve()
        if scenario_root.parent != self.root:
            raise DemoScenarioError("demo scenario path is outside the catalog")
        metrics_path = (scenario_root / "metrics.csv").resolve()
        document_path = (scenario_root / "strategy.md").resolve()
        for path in (metrics_path, document_path):
            if path.parent != scenario_root:
                raise DemoScenarioError("demo scenario file is outside the catalog")
            if not path.is_file():
                raise DemoScenarioError(f"demo scenario is missing {path.name}")
        return metrics_path, document_path


def _parse_scenario(value: object) -> DemoScenario:
    if not isinstance(value, dict) or set(value) != SCENARIO_FIELDS:
        raise DemoScenarioError("demo scenario metadata fields are invalid")
    scenario_id = value["id"]
    if not isinstance(scenario_id, str) or SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None:
        raise DemoScenarioError("invalid demo scenario ID")
    text_values = {key: value[key] for key in SCENARIO_FIELDS - {"id", "expected_validation"}}
    if any(not isinstance(text, str) or not text.strip() for text in text_values.values()):
        raise DemoScenarioError("demo scenario metadata must be non-empty text")
    expected_validation = value["expected_validation"]
    if not isinstance(expected_validation, str) or expected_validation not in VALIDATION_STATES:
        raise DemoScenarioError("demo scenario expected validation state is invalid")
    return DemoScenario(
        id=scenario_id,
        label=value["label"],
        summary=value["summary"],
        suggested_question=value["suggested_question"],
        learning_objective=value["learning_objective"],
        expected_validation=expected_validation,
    )
