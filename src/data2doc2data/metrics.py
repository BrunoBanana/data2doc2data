"""Configurable metric definitions and deterministic signal calculation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import math
from typing import Literal


Aggregation = Literal["mean", "sum", "latest", "min", "max"]
Comparison = Literal["split_window", "previous_period"]
DuplicatePolicy = Literal["reject", "mean", "sum"]

SUPPORTED_AGGREGATIONS = {"mean", "sum", "latest", "min", "max"}
SUPPORTED_COMPARISONS = {"split_window", "previous_period"}
SUPPORTED_DUPLICATE_POLICIES = {"reject", "mean", "sum"}


class InputValidationError(ValueError):
    """Raised when inputs cannot produce a trustworthy metric signal."""


@dataclass(frozen=True)
class MetricRow:
    date: date
    metric: str
    value: float
    source_row: int | None = None


@dataclass(frozen=True)
class MetricSpec:
    name: str
    aliases: tuple[str, ...] = ()
    display_name: str | None = None
    unit: str | None = None
    aggregation: Aggregation = "mean"
    comparison: Comparison = "split_window"
    threshold: float = 1.0
    minimum_observations: int = 2
    duplicate_policy: DuplicatePolicy = "reject"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InputValidationError("metric name is required")
        if self.aggregation not in SUPPORTED_AGGREGATIONS:
            raise InputValidationError(f"unsupported aggregation: {self.aggregation}")
        if self.comparison not in SUPPORTED_COMPARISONS:
            raise InputValidationError(f"unsupported comparison: {self.comparison}")
        if not math.isfinite(self.threshold) or self.threshold < 0:
            raise InputValidationError("threshold must be a finite non-negative number")
        if self.minimum_observations < 2:
            raise InputValidationError("minimum observations must be at least two")
        if self.duplicate_policy not in SUPPORTED_DUPLICATE_POLICIES:
            raise InputValidationError(f"unsupported duplicate policy: {self.duplicate_policy}")


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class Signal:
    metric: str
    baseline: float
    current: float
    change_percent: float | None
    direction: str
    summary: str
    baseline_count: int = 0
    current_count: int = 0
    baseline_range: DateRange | None = None
    current_range: DateRange | None = None
    absolute_change: float = 0.0
    spec: MetricSpec | None = None


class SignalEngine:
    """Build auditable before/after signals from dated metric observations."""

    def build(self, spec: MetricSpec, rows: list[MetricRow]) -> Signal:
        metric_rows = [row for row in rows if row.metric == spec.name]
        for row in metric_rows:
            if not math.isfinite(row.value):
                raise InputValidationError("metric values must be finite numbers")

        ordered_rows = self._resolve_duplicates(spec, metric_rows)
        if len(ordered_rows) < spec.minimum_observations:
            minimum = "two" if spec.minimum_observations == 2 else str(spec.minimum_observations)
            raise InputValidationError(
                f"Metric '{spec.name}' needs at least {minimum} dated observations."
            )

        baseline_rows, current_rows = self._comparison_windows(spec.comparison, ordered_rows)
        baseline = self._aggregate(spec.aggregation, baseline_rows)
        current = self._aggregate(spec.aggregation, current_rows)
        absolute_change = current - baseline
        change_percent = None if baseline == 0 else (absolute_change / abs(baseline)) * 100
        comparison_change = absolute_change if spec.unit is not None or change_percent is None else change_percent
        comparison_threshold = 0.0 if spec.unit is None and change_percent is None else spec.threshold
        direction = (
            "up"
            if comparison_change > comparison_threshold
            else "down"
            if comparison_change < -comparison_threshold
            else "flat"
        )

        display_name = spec.display_name or spec.name
        unit = spec.unit or ""
        direction_label = {"up": "上升", "down": "下降", "flat": "基本持平"}[direction]
        change_summary = "相对变化不适用" if change_percent is None else f"{change_percent:+.1f}%"
        summary = (
            f"{display_name}从 {baseline:.2f}{unit} 变为 {current:.2f}{unit}"
            f"（{change_summary}），呈{direction_label}趋势。"
        )
        return Signal(
            metric=spec.name,
            baseline=baseline,
            current=current,
            change_percent=change_percent,
            direction=direction,
            summary=summary,
            baseline_count=len(baseline_rows),
            current_count=len(current_rows),
            baseline_range=DateRange(baseline_rows[0].date, baseline_rows[-1].date),
            current_range=DateRange(current_rows[0].date, current_rows[-1].date),
            absolute_change=absolute_change,
            spec=spec,
        )

    @staticmethod
    def _comparison_windows(
        comparison: Comparison,
        rows: list[MetricRow],
    ) -> tuple[list[MetricRow], list[MetricRow]]:
        midpoint = max(1, len(rows) // 2)
        if comparison == "previous_period":
            return rows[-(midpoint * 2) : -midpoint], rows[-midpoint:]
        return rows[:midpoint], rows[midpoint:]

    @staticmethod
    def _resolve_duplicates(spec: MetricSpec, rows: list[MetricRow]) -> list[MetricRow]:
        grouped: dict[date, list[MetricRow]] = defaultdict(list)
        for row in rows:
            grouped[row.date].append(row)

        resolved = []
        for row_date in sorted(grouped):
            same_date = grouped[row_date]
            if len(same_date) > 1 and spec.duplicate_policy == "reject":
                raise InputValidationError(
                    f"Metric '{spec.name}' has duplicate observations for {row_date.isoformat()}."
                )
            values = [row.value for row in same_date]
            value = (
                sum(values)
                if spec.duplicate_policy == "sum"
                else sum(values) / len(values)
                if spec.duplicate_policy == "mean"
                else values[0]
            )
            resolved.append(MetricRow(row_date, spec.name, value))
        return resolved

    @staticmethod
    def _aggregate(aggregation: Aggregation, rows: list[MetricRow]) -> float:
        values = [row.value for row in rows]
        if aggregation == "sum":
            return sum(values)
        if aggregation == "latest":
            return values[-1]
        if aggregation == "min":
            return min(values)
        if aggregation == "max":
            return max(values)
        return sum(values) / len(values)
