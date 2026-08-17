"""Declarative, user-owned business assumption rules.

A ruleset is the auditable contract between a user (or an agent proposal)
and the deterministic evidence engine. It declares the metrics that exist,
how each metric is measured, and the named multi-metric rules the engine
may verdict on. Rules are data, not code: they are loaded from a bounded
local JSON document and validated strictly before any file is trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from .hypotheses import HypothesisClause, HypothesisSpec
from .metrics import (
    SUPPORTED_AGGREGATIONS,
    SUPPORTED_COMPARISONS,
    SUPPORTED_DUPLICATE_POLICIES,
    InputValidationError,
    MetricSpec,
)


RULESET_VERSION = 1
MAX_RULES_BYTES = 262_144
MAX_METRICS = 100
MAX_RULES = 50
MAX_CLAUSES_PER_RULE = 20
MAX_ALIASES_PER_METRIC = 12

_METRIC_NAME_PATTERN = re.compile(r"[a-zA-Z0-9_.\-]{1,128}")
_RULE_ID_PATTERN = re.compile(r"[a-zA-Z0-9_.\-]{1,64}")


class RulesError(InputValidationError):
    """Raised when a declarative ruleset cannot be trusted."""


@dataclass(frozen=True)
class MetricDefinition:
    """How a single metric is named, displayed, and measured."""

    name: str
    aliases: tuple[str, ...] = ()
    display_name: str | None = None
    unit: str | None = None
    aggregation: str = "mean"
    comparison: str = "split_window"
    threshold: float = 1.0
    minimum_observations: int = 2
    duplicate_policy: str = "reject"

    def to_spec(self) -> MetricSpec:
        return MetricSpec(
            name=self.name,
            aliases=self.aliases,
            display_name=self.display_name,
            unit=self.unit,
            aggregation=self.aggregation,
            comparison=self.comparison,
            threshold=self.threshold,
            minimum_observations=self.minimum_observations,
            duplicate_policy=self.duplicate_policy,
        )


@dataclass(frozen=True)
class Rule:
    """A named, auditable multi-metric assumption."""

    rule_id: str
    name: str
    clauses: tuple[HypothesisClause, ...]
    description: str = ""

    def hypothesis(self) -> HypothesisSpec:
        return HypothesisSpec(self.clauses)

    def metric_set(self) -> frozenset[str]:
        return frozenset(clause.metric for clause in self.clauses)


@dataclass(frozen=True)
class RuleSet:
    """The full declarative contract: metric definitions plus named rules."""

    metrics: dict[str, MetricDefinition]
    rules: tuple[Rule, ...] = ()
    version: int = RULESET_VERSION

    def aliases(self) -> dict[str, tuple[str, ...]]:
        return {name: definition.aliases for name, definition in self.metrics.items()}

    def spec_for(self, metric: str) -> MetricSpec:
        definition = self.metrics.get(metric)
        if definition is None:
            return MetricSpec(name=metric)
        return definition.to_spec()

    def display_name(self, metric: str) -> str:
        definition = self.metrics.get(metric)
        if definition and definition.display_name:
            return definition.display_name
        return metric

    def match_rule(self, hypothesis: HypothesisSpec) -> Rule | None:
        """Match a document-derived hypothesis to a declared rule by metric set.

        The document only triggers verification; the rule's declared
        directions are the contract being verified.
        """
        parsed_metrics = frozenset(clause.metric for clause in hypothesis.clauses)
        for rule in self.rules:
            if rule.metric_set() == parsed_metrics:
                return rule
        return None


def default_ruleset() -> RuleSet:
    """Built-in contract that reproduces the historical behavior exactly."""
    return RuleSet(
        metrics={
            "retention_rate": MetricDefinition(
                name="retention_rate",
                aliases=("retention", "retention rate", "留存", "留存率"),
                display_name="留存率",
            ),
            "activation_rate": MetricDefinition(
                name="activation_rate",
                aliases=("activation", "activation rate", "激活", "激活率"),
                display_name="激活率",
            ),
        }
    )


def load_ruleset(path: Path) -> RuleSet:
    """Load and strictly validate a ruleset from a bounded local JSON file."""
    rules_path = Path(path).expanduser()
    try:
        if not rules_path.is_file():
            raise RulesError("rules file does not exist")
        if rules_path.stat().st_size > MAX_RULES_BYTES:
            raise RulesError(f"rules file is too large; limit is {MAX_RULES_BYTES} bytes")
        raw = rules_path.read_bytes()
        if len(raw) > MAX_RULES_BYTES:
            raise RulesError(f"rules file is too large; limit is {MAX_RULES_BYTES} bytes")
        payload = json.loads(raw.decode("utf-8"))
    except RulesError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RulesError(f"cannot read rules file: {error}") from error
    return parse_ruleset(payload)


def parse_ruleset(payload: object) -> RuleSet:
    """Validate an untrusted ruleset document before it reaches the engine."""
    if not isinstance(payload, dict):
        raise RulesError("ruleset must be a JSON object")
    version = payload.get("version", RULESET_VERSION)
    if version != RULESET_VERSION:
        raise RulesError(f"unsupported ruleset version: {version!r}")

    metrics = _parse_metrics(payload.get("metrics"))
    rules = _parse_rules(payload.get("rules", []), metrics)
    return RuleSet(metrics=metrics, rules=rules)


def _parse_metrics(raw_metrics: object) -> dict[str, MetricDefinition]:
    if not isinstance(raw_metrics, dict) or not 1 <= len(raw_metrics) <= MAX_METRICS:
        raise RulesError(f"ruleset metrics must be an object with 1 to {MAX_METRICS} entries")
    metrics: dict[str, MetricDefinition] = {}
    for name, raw_definition in raw_metrics.items():
        if not isinstance(name, str) or not _METRIC_NAME_PATTERN.fullmatch(name):
            raise RulesError(f"invalid metric name: {name!r}")
        normalized = name.lower()
        if normalized in metrics:
            raise RulesError(f"duplicate metric definition: {normalized}")
        if not isinstance(raw_definition, dict):
            raise RulesError(f"metric definition for '{normalized}' must be an object")
        metrics[normalized] = _parse_metric_definition(normalized, raw_definition)
    return metrics


def _parse_metric_definition(name: str, raw: dict) -> MetricDefinition:
    aliases = raw.get("aliases", [])
    if not isinstance(aliases, list) or len(aliases) > MAX_ALIASES_PER_METRIC:
        raise RulesError(f"aliases for '{name}' must be a list of at most {MAX_ALIASES_PER_METRIC} items")
    parsed_aliases = []
    for alias in aliases:
        if not isinstance(alias, str) or not alias.strip() or len(alias) > 64:
            raise RulesError(f"each alias for '{name}' must be text of at most 64 characters")
        parsed_aliases.append(alias.strip())

    display_name = raw.get("display_name")
    if display_name is not None and (not isinstance(display_name, str) or len(display_name) > 64):
        raise RulesError(f"display_name for '{name}' must be text of at most 64 characters")
    unit = raw.get("unit")
    if unit is not None and (not isinstance(unit, str) or len(unit) > 16):
        raise RulesError(f"unit for '{name}' must be text of at most 16 characters")

    aggregation = raw.get("aggregation", "mean")
    if aggregation not in SUPPORTED_AGGREGATIONS:
        raise RulesError(f"unsupported aggregation for '{name}': {aggregation!r}")
    comparison = raw.get("comparison", "split_window")
    if comparison not in SUPPORTED_COMPARISONS:
        raise RulesError(f"unsupported comparison for '{name}': {comparison!r}")
    duplicate_policy = raw.get("duplicate_policy", "reject")
    if duplicate_policy not in SUPPORTED_DUPLICATE_POLICIES:
        raise RulesError(f"unsupported duplicate_policy for '{name}': {duplicate_policy!r}")

    threshold = raw.get("threshold", 1.0)
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise RulesError(f"threshold for '{name}' must be a number")
    if not math.isfinite(threshold) or threshold < 0:
        raise RulesError(f"threshold for '{name}' must be a finite non-negative number")

    minimum_observations = raw.get("minimum_observations", 2)
    if isinstance(minimum_observations, bool) or not isinstance(minimum_observations, int):
        raise RulesError(f"minimum_observations for '{name}' must be an integer")
    if not 2 <= minimum_observations <= 1000:
        raise RulesError(f"minimum_observations for '{name}' must be between 2 and 1000")

    return MetricDefinition(
        name=name,
        aliases=tuple(parsed_aliases),
        display_name=display_name,
        unit=unit,
        aggregation=aggregation,
        comparison=comparison,
        threshold=float(threshold),
        minimum_observations=minimum_observations,
        duplicate_policy=duplicate_policy,
    )


def _parse_rules(raw_rules: object, metrics: dict[str, MetricDefinition]) -> tuple[Rule, ...]:
    if not isinstance(raw_rules, list) or len(raw_rules) > MAX_RULES:
        raise RulesError(f"rules must be a list of at most {MAX_RULES} items")
    rules = []
    seen_ids: set[str] = set()
    seen_metric_sets: set[frozenset[str]] = set()
    for raw_rule in raw_rules:
        if not isinstance(raw_rule, dict):
            raise RulesError("each rule must be an object")
        rule = _parse_rule(raw_rule, metrics)
        if rule.rule_id in seen_ids:
            raise RulesError(f"duplicate rule id: {rule.rule_id}")
        if rule.metric_set() in seen_metric_sets:
            raise RulesError(f"duplicate rule for metric set: {sorted(rule.metric_set())}")
        seen_ids.add(rule.rule_id)
        seen_metric_sets.add(rule.metric_set())
        rules.append(rule)
    return tuple(rules)


def _parse_rule(raw_rule: dict, metrics: dict[str, MetricDefinition]) -> Rule:
    rule_id = raw_rule.get("id")
    if not isinstance(rule_id, str) or not _RULE_ID_PATTERN.fullmatch(rule_id):
        raise RulesError("rule id must be 1-64 characters of letters, digits, '_', '.', '-'")
    name = raw_rule.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 128:
        raise RulesError(f"rule '{rule_id}' name must be text of at most 128 characters")
    description = raw_rule.get("description", "")
    if not isinstance(description, str) or len(description) > 512:
        raise RulesError(f"rule '{rule_id}' description must be text of at most 512 characters")

    raw_clauses = raw_rule.get("clauses")
    if not isinstance(raw_clauses, list) or not 1 <= len(raw_clauses) <= MAX_CLAUSES_PER_RULE:
        raise RulesError(f"rule '{rule_id}' must declare 1 to {MAX_CLAUSES_PER_RULE} clauses")
    clauses = []
    seen_metrics: set[str] = set()
    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, dict):
            raise RulesError(f"each clause of rule '{rule_id}' must be an object")
        metric = raw_clause.get("metric")
        direction = raw_clause.get("direction")
        if not isinstance(metric, str):
            raise RulesError(f"clause metric of rule '{rule_id}' must be text")
        normalized_metric = metric.strip().lower()
        if normalized_metric not in metrics:
            raise RulesError(
                f"rule '{rule_id}' references undeclared metric: {normalized_metric!r}"
            )
        if direction not in {"up", "down", "flat"}:
            raise RulesError(f"clause direction of rule '{rule_id}' must be up, down, or flat")
        if normalized_metric in seen_metrics:
            raise RulesError(f"rule '{rule_id}' repeats metric: {normalized_metric}")
        seen_metrics.add(normalized_metric)
        clauses.append(HypothesisClause(normalized_metric, direction))
    return Rule(rule_id, name.strip(), tuple(clauses), description)
