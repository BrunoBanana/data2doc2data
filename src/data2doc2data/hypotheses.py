"""Structured, deterministic metric hypotheses and clause verification."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .metrics import InputValidationError, MetricRow, MetricSpec, SignalEngine


Direction = Literal["up", "down", "flat"]
ClauseStatus = Literal["confirmed", "contradicted", "unavailable"]
HypothesisStatus = Literal["confirmed", "contradicted", "unavailable"]
HypothesisSource = Literal["deterministic", "agent_proposed", "user_confirmed"]

DEFAULT_ALIASES = {
    "retention_rate": ("retention rate", "retention", "留存率", "留存"),
    "activation_rate": ("activation rate", "activation", "激活率", "激活"),
}
NEGATION_PATTERNS = (
    r"不能说明",
    r"无法说明",
    r"没有证据",
    r"无证据",
    r"未能",
    r"\bcannot\b",
    r"\bcan't\b",
    r"\bdoes not\b",
    r"\bdid not\b",
    r"\bno evidence\b",
)
ENGLISH_DIRECTIONS = {
    "up": r"rises?|rose|increases?|increased|improves?|improved|grows?|grew|went up|trends? up",
    "down": r"falls?|fell|decreases?|decreased|declines?|declined|drops?|dropped|went down|trends? down",
    "flat": r"flat|stable|unchanged|holds? steady|remains? stable",
}
CHINESE_DIRECTIONS = {
    "up": r"上升|提高|增长|上涨",
    "down": r"下降|降低|下滑|下跌",
    "flat": r"持平|稳定|不变",
}


@dataclass(frozen=True)
class HypothesisClause:
    metric: str
    direction: Direction

    def __post_init__(self) -> None:
        if not self.metric or self.direction not in {"up", "down", "flat"}:
            raise InputValidationError("hypothesis clause has an invalid metric or direction")


@dataclass(frozen=True)
class HypothesisSpec:
    clauses: tuple[HypothesisClause, ...]
    time_relation: Literal["same_window"] = "same_window"
    source: HypothesisSource = "deterministic"

    def __post_init__(self) -> None:
        if not self.clauses:
            raise InputValidationError("hypothesis must contain at least one clause")
        if self.time_relation != "same_window":
            raise InputValidationError("unsupported hypothesis time relation")
        if self.source not in {"deterministic", "agent_proposed", "user_confirmed"}:
            raise InputValidationError("unsupported hypothesis source")


@dataclass(frozen=True)
class ClauseVerification:
    metric: str
    expected_direction: Direction
    observed_direction: Direction | None
    status: ClauseStatus
    summary: str


@dataclass(frozen=True)
class HypothesisVerification:
    status: HypothesisStatus
    clauses: tuple[ClauseVerification, ...]
    summary: str


def parse_controlled_hypothesis(
    text: str,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> HypothesisSpec | None:
    """Parse adjacent metric-direction phrases; ambiguous or negated text is not evidence."""
    normalized = " ".join(text.lower().split())
    if any(re.search(pattern, normalized) for pattern in NEGATION_PATTERNS):
        return None

    matches: list[tuple[int, int, HypothesisClause]] = []
    alias_map = DEFAULT_ALIASES if aliases is None else aliases
    for metric, metric_aliases in alias_map.items():
        for alias in sorted(metric_aliases, key=len, reverse=True):
            if re.search(r"[\u4e00-\u9fff]", alias):
                for direction, terms in CHINESE_DIRECTIONS.items():
                    pattern = rf"{re.escape(alias)}[\s，、,:：]*(?:{terms})"
                    matches.extend(
                        (match.start(), match.end(), HypothesisClause(metric, direction))
                        for match in re.finditer(pattern, normalized)
                    )
            else:
                for direction, terms in ENGLISH_DIRECTIONS.items():
                    pattern = rf"\b{re.escape(alias)}\b(?:\s+[a-z]+){{0,2}}?\s+(?:{terms})\b"
                    matches.extend(
                        (match.start(), match.end(), HypothesisClause(metric, direction))
                        for match in re.finditer(pattern, normalized)
                    )

    clauses = []
    occupied: list[tuple[int, int, str]] = []
    for start, end, clause in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        overlaps_alias = any(
            metric == clause.metric and not (end <= seen_start or start >= seen_end)
            for seen_start, seen_end, metric in occupied
        )
        if overlaps_alias:
            continue
        clauses.append((start, clause))
        occupied.append((start, end, clause.metric))
    if not clauses:
        return None
    ordered_clauses = tuple(clause for _, clause in sorted(clauses, key=lambda item: item[0]))
    if len({clause.metric for clause in ordered_clauses}) != len(ordered_clauses):
        return None
    return HypothesisSpec(ordered_clauses)


def validate_hypothesis_payload(payload: object) -> HypothesisSpec:
    """Validate untrusted agent JSON before it reaches the evidence engine."""
    if not isinstance(payload, dict):
        raise InputValidationError("hypothesis payload must be an object")
    raw_clauses = payload.get("clauses")
    if not isinstance(raw_clauses, list) or not 1 <= len(raw_clauses) <= 20:
        raise InputValidationError("hypothesis clauses must contain between 1 and 20 items")

    clauses = []
    seen_metrics = set()
    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, dict):
            raise InputValidationError("each hypothesis clause must be an object")
        metric = raw_clause.get("metric")
        direction = raw_clause.get("direction")
        if not isinstance(metric, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", metric):
            raise InputValidationError("clause metric must be a normalized metric name")
        if direction not in {"up", "down", "flat"}:
            raise InputValidationError("clause direction must be up, down, or flat")
        if metric in seen_metrics:
            raise InputValidationError(f"duplicate hypothesis metric: {metric}")
        seen_metrics.add(metric)
        clauses.append(HypothesisClause(metric, direction))

    time_relation = payload.get("time_relation", "same_window")
    if time_relation != "same_window":
        raise InputValidationError("unsupported hypothesis time relation")
    source = payload.get("source", "agent_proposed")
    if source not in {"deterministic", "agent_proposed", "user_confirmed"}:
        raise InputValidationError("unsupported hypothesis source")
    return HypothesisSpec(tuple(clauses), time_relation, source)


def verify_hypothesis(
    hypothesis: HypothesisSpec,
    rows: list[MetricRow],
    specs: dict[str, MetricSpec] | None = None,
) -> HypothesisVerification:
    """Verify each clause independently; agents cannot supply observed results."""
    results = []
    for clause in hypothesis.clauses:
        spec = (specs or {}).get(clause.metric, MetricSpec(name=clause.metric))
        try:
            signal = SignalEngine().build(spec, rows)
        except InputValidationError:
            results.append(
                ClauseVerification(
                    clause.metric,
                    clause.direction,
                    None,
                    "unavailable",
                    f"指标 {clause.metric} 缺少可验证数据。",
                )
            )
            continue
        status = "confirmed" if signal.direction == clause.direction else "contradicted"
        results.append(
            ClauseVerification(
                clause.metric,
                clause.direction,
                signal.direction,
                status,
                f"指标 {clause.metric} 实测方向为 {signal.direction}，预期为 {clause.direction}。",
            )
        )

    if any(result.status == "contradicted" for result in results):
        status = "contradicted"
    elif any(result.status == "unavailable" for result in results):
        status = "unavailable"
    else:
        status = "confirmed"
    summary = " ".join(result.summary for result in results)
    return HypothesisVerification(status, tuple(results), summary)
