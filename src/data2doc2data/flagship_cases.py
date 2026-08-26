"""Strict, path-safe catalog for complete built-in synthetic analysis cases."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import re
from typing import Mapping

from .rules import RulesError, load_ruleset


CATALOG_VERSION = 1
CASE_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CATALOG_FIELDS = frozenset({"version", "cases"})
CASE_FIELDS = frozenset(
    {
        "id",
        "title",
        "summary",
        "business_question",
        "learning_objective",
        "synthetic",
        "record_count",
        "metrics",
        "documents",
        "time_range",
    }
)
TIME_RANGE_FIELDS = frozenset({"start", "end", "grain"})
METRIC_FIELDS = ("date", "metric", "value", "segment", "unit")


class FlagshipCaseError(ValueError):
    """Raised when a bundled flagship case violates its public contract."""


@dataclass(frozen=True)
class FlagshipCase:
    id: str
    title: str
    summary: str
    business_question: str
    learning_objective: str
    synthetic: bool
    record_count: int
    metrics: tuple[str, ...]
    documents: tuple[str, ...]
    start_date: str
    end_date: str
    grain: str

    @property
    def metric_count(self) -> int:
        return len(self.metrics)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def to_summary_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "business_question": self.business_question,
            "learning_objective": self.learning_objective,
            "synthetic": self.synthetic,
            "record_count": self.record_count,
            "metric_count": self.metric_count,
            "document_count": self.document_count,
            "time_range": {"start": self.start_date, "end": self.end_date, "grain": self.grain},
        }


@dataclass(frozen=True)
class FlagshipCasePackage:
    case: FlagshipCase
    root: Path
    metrics_path: Path
    document_paths: tuple[Path, ...]
    rules_path: Path
    hypotheses_path: Path
    expected_path: Path
    demo_flow_path: Path


class FlagshipCaseCatalog:
    def __init__(self, root: Path, packages: tuple[FlagshipCasePackage, ...]) -> None:
        self.root = root
        self._packages = packages
        self._by_id = {package.case.id: package for package in packages}

    @classmethod
    def load(cls, root: Path | None = None) -> FlagshipCaseCatalog:
        catalog_root = (
            root.expanduser().resolve()
            if root is not None
            else (Path(__file__).resolve().parent / "sample" / "cases").resolve()
        )
        payload = _read_json(catalog_root / "catalog.json", "flagship case catalog")
        if set(payload) != CATALOG_FIELDS or payload.get("version") != CATALOG_VERSION:
            raise FlagshipCaseError("flagship case catalog fields or version are invalid")
        case_ids = payload.get("cases")
        if not isinstance(case_ids, list) or not case_ids:
            raise FlagshipCaseError("flagship case catalog must contain cases")
        if any(not isinstance(case_id, str) or CASE_ID_PATTERN.fullmatch(case_id) is None for case_id in case_ids):
            raise FlagshipCaseError("invalid flagship case ID")
        if len(case_ids) != len(set(case_ids)):
            raise FlagshipCaseError("flagship case catalog contains duplicate IDs")
        packages = tuple(_load_package(catalog_root, case_id) for case_id in case_ids)
        return cls(catalog_root, packages)

    def list(self) -> tuple[FlagshipCase, ...]:
        return tuple(package.case for package in self._packages)

    def package(self, case_id: str) -> FlagshipCasePackage:
        if not isinstance(case_id, str) or CASE_ID_PATTERN.fullmatch(case_id) is None:
            raise FlagshipCaseError("invalid flagship case ID")
        try:
            return self._by_id[case_id]
        except KeyError as error:
            raise FlagshipCaseError("unknown flagship case ID") from error


def _load_package(catalog_root: Path, case_id: str) -> FlagshipCasePackage:
    case_root = _contained(catalog_root, catalog_root / case_id)
    metadata = _read_json(_contained(case_root, case_root / "case.json"), "flagship case metadata")
    case = _parse_case(metadata, case_id)
    metrics_path = _contained_file(case_root, case_root / "metrics.csv")
    document_paths = tuple(
        _contained_file(case_root, case_root / "documents" / filename) for filename in case.documents
    )
    rules_path = _contained_file(case_root, case_root / "rules.json")
    hypotheses_path = _contained_file(case_root, case_root / "hypotheses.json")
    expected_path = _contained_file(case_root, case_root / "expected.json")
    demo_flow_path = _contained_file(case_root, case_root / "demo-flow.json")
    _validate_companion(_read_json(rules_path, "flagship case rules"), "rules", {"version", "metrics", "rules"})
    try:
        load_ruleset(rules_path)
    except RulesError as error:
        raise FlagshipCaseError(f"flagship case rules are invalid: {error}") from error
    _validate_companion(
        _read_json(hypotheses_path, "flagship case hypotheses"),
        "hypotheses",
        {"version", "hypotheses"},
    )
    _validate_expected(_read_json(expected_path, "flagship case expected outcomes"))
    demo_flow = _read_json(demo_flow_path, "flagship case demo flow")
    _validate_companion(
        demo_flow,
        "demo flow",
        {"version", "runner", "use_bundled_hypotheses", "stages"},
    )
    if (
        demo_flow.get("runner") != "demo"
        or demo_flow.get("use_bundled_hypotheses") is not True
        or not isinstance(demo_flow.get("stages"), list)
    ):
        raise FlagshipCaseError("flagship case demo flow is invalid")
    _validate_metrics(metrics_path, case)
    return FlagshipCasePackage(
        case=case,
        root=case_root,
        metrics_path=metrics_path,
        document_paths=document_paths,
        rules_path=rules_path,
        hypotheses_path=hypotheses_path,
        expected_path=expected_path,
        demo_flow_path=demo_flow_path,
    )


def _parse_case(value: Mapping[str, object], expected_id: str) -> FlagshipCase:
    if set(value) != CASE_FIELDS or value.get("id") != expected_id:
        raise FlagshipCaseError("flagship case metadata fields or ID are invalid")
    for field in ("title", "summary", "business_question", "learning_objective"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            raise FlagshipCaseError(f"flagship case {field} must be non-empty text")
    if value.get("synthetic") is not True:
        raise FlagshipCaseError("flagship case must be explicitly synthetic")
    record_count = value.get("record_count")
    if type(record_count) is not int or record_count < 200:
        raise FlagshipCaseError("flagship case must contain at least 200 records")
    metrics = _text_list(value.get("metrics"), "metrics", minimum=8)
    documents = _text_list(value.get("documents"), "documents", minimum=4)
    if len(metrics) != len(set(metrics)) or len(documents) != len(set(documents)):
        raise FlagshipCaseError("flagship case metrics and documents must be unique")
    if any(Path(filename).name != filename or not filename.endswith(".md") for filename in documents):
        raise FlagshipCaseError("flagship case document names are invalid")
    time_range = value.get("time_range")
    if not isinstance(time_range, Mapping) or set(time_range) != TIME_RANGE_FIELDS:
        raise FlagshipCaseError("flagship case time range is invalid")
    start = _iso_date(time_range.get("start"), "start")
    end = _iso_date(time_range.get("end"), "end")
    if start > end or time_range.get("grain") != "week":
        raise FlagshipCaseError("flagship case time range is invalid")
    return FlagshipCase(
        id=expected_id,
        title=str(value["title"]),
        summary=str(value["summary"]),
        business_question=str(value["business_question"]),
        learning_objective=str(value["learning_objective"]),
        synthetic=True,
        record_count=record_count,
        metrics=metrics,
        documents=documents,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        grain="week",
    )


def _validate_metrics(path: Path, case: FlagshipCase) -> None:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != METRIC_FIELDS:
                raise FlagshipCaseError("flagship case metric fields are invalid")
            rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as error:
        raise FlagshipCaseError("cannot read flagship case metrics") from error
    seen: set[tuple[str, str, str]] = set()
    observed_metrics: set[str] = set()
    for row in rows:
        current_date = _iso_date(row.get("date"), "metric date")
        metric = row.get("metric", "")
        segment = row.get("segment", "")
        unit = row.get("unit", "")
        if metric not in case.metrics or not segment.strip() or not unit.strip():
            raise FlagshipCaseError("flagship case metric row is invalid")
        try:
            number = float(row.get("value", ""))
        except ValueError as error:
            raise FlagshipCaseError("flagship case metric value is invalid") from error
        if not math.isfinite(number):
            raise FlagshipCaseError("flagship case metric value must be finite")
        key = (current_date.isoformat(), metric, segment)
        if key in seen:
            raise FlagshipCaseError("duplicate metric record")
        seen.add(key)
        observed_metrics.add(metric)
    if len(rows) != case.record_count:
        raise FlagshipCaseError("flagship case record count does not match metadata")
    if observed_metrics != set(case.metrics):
        raise FlagshipCaseError("flagship case metrics do not match metadata")


def _read_json(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FlagshipCaseError(f"cannot read {label}") from error
    if not isinstance(value, dict):
        raise FlagshipCaseError(f"{label} must be a JSON object")
    return value


def _validate_companion(value: Mapping[str, object], label: str, fields: set[str]) -> None:
    if set(value) != fields or value.get("version") != 1:
        raise FlagshipCaseError(f"flagship case {label} fields are invalid")


def _validate_expected(value: Mapping[str, object]) -> None:
    allowed = ({"version", "outcomes"}, {"version", "outcomes", "analysis_truth"})
    if set(value) not in allowed or value.get("version") != 1 or not isinstance(value.get("outcomes"), list):
        raise FlagshipCaseError("flagship case expected outcomes fields are invalid")
    truth = value.get("analysis_truth")
    if truth is None:
        return
    fields = {
        "primary_metric",
        "anomaly_dates",
        "change_date",
        "topic_keywords",
        "representative_documents",
        "cycle_tools",
    }
    if not isinstance(truth, Mapping) or set(truth) != fields:
        raise FlagshipCaseError("flagship case analysis truth fields are invalid")
    if not isinstance(truth.get("primary_metric"), str) or not isinstance(truth.get("change_date"), str):
        raise FlagshipCaseError("flagship case analysis truth metrics or dates are invalid")
    for field in ("anomaly_dates", "topic_keywords", "representative_documents", "cycle_tools"):
        if not isinstance(truth.get(field), list) or any(not isinstance(item, str) for item in truth[field]):
            raise FlagshipCaseError(f"flagship case analysis truth {field} is invalid")


def _contained(root: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    if resolved == root or root not in resolved.parents:
        raise FlagshipCaseError("path is outside the flagship case package")
    return resolved


def _contained_file(root: Path, candidate: Path) -> Path:
    resolved = _contained(root, candidate)
    if not resolved.is_file():
        raise FlagshipCaseError(f"flagship case is missing {candidate.name}")
    return resolved


def _text_list(value: object, label: str, *, minimum: int) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) < minimum:
        raise FlagshipCaseError(f"flagship case requires at least {minimum} {label}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise FlagshipCaseError(f"flagship case {label} must be non-empty text")
    return tuple(value)


def _iso_date(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise FlagshipCaseError(f"flagship case {label} is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise FlagshipCaseError(f"flagship case {label} is invalid") from error
