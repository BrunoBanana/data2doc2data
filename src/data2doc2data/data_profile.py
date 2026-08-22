"""Model-free profiling and default dashboard planning for standard metric CSV snapshots."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import math
from pathlib import Path
from statistics import fmean

from .analysis import MAX_CSV_BYTES
from .dashboard import DashboardBlock, DashboardSpec, FlintChartSpec, QueryProvenance


class DataProfileError(ValueError):
    pass


@dataclass(frozen=True)
class MetricSummary:
    count: int
    minimum: float
    maximum: float
    average: float


@dataclass(frozen=True)
class DataProfile:
    snapshot_id: str
    sha256: str
    row_count: int
    field_count: int
    date_range: tuple[str, str]
    metrics: tuple[str, ...]
    missing_count: int
    duplicate_count: int
    metric_summaries: dict[str, MetricSummary]
    trend_points: tuple[dict[str, object], ...]


def profile_standard_csv(path: Path, snapshot_id: str) -> DataProfile:
    try:
        content = path.read_bytes()
        if not content or len(content) > MAX_CSV_BYTES:
            raise DataProfileError("CSV source is empty or oversized")
        digest = hashlib.sha256(content).hexdigest()
        text = content.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        required = {"date", "metric", "value"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise DataProfileError("CSV must include date, metric, value columns")
        rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise DataProfileError(f"cannot profile CSV: {exc}") from exc
    if not rows:
        raise DataProfileError("CSV has no data rows")

    missing_count = 0
    parsed: list[tuple[str, str, float]] = []
    for row in rows:
        raw_date = (row.get("date") or "").strip()
        metric = (row.get("metric") or "").strip()
        raw_value = (row.get("value") or "").strip()
        if not raw_date or not metric or not raw_value:
            missing_count += sum(not value for value in (raw_date, metric, raw_value))
            continue
        try:
            parsed_date = date.fromisoformat(raw_date).isoformat()
            value = float(raw_value)
        except ValueError as exc:
            raise DataProfileError(f"CSV contains an invalid date or value: {exc}") from exc
        if not math.isfinite(value):
            raise DataProfileError("CSV values must be finite")
        parsed.append((parsed_date, metric, value))
    if not parsed:
        raise DataProfileError("CSV has no valid metric rows")

    duplicates = len(parsed) - len(set(parsed))
    dates = sorted({item[0] for item in parsed})
    metric_names = sorted({item[1] for item in parsed})
    summaries = {}
    for metric in metric_names:
        values = [item[2] for item in parsed if item[1] == metric]
        summaries[metric] = MetricSummary(len(values), min(values), max(values), fmean(values))
    aggregates: dict[tuple[str, str], list[float]] = {}
    for item_date, metric, value in parsed:
        aggregates.setdefault((item_date, metric), []).append(value)
    points = tuple(
        {"date": item_date, "metric": metric, "value": fmean(values)}
        for (item_date, metric), values in sorted(aggregates.items())[:1000]
    )
    return DataProfile(
        snapshot_id=snapshot_id,
        sha256=digest,
        row_count=len(rows),
        field_count=len(reader.fieldnames),
        date_range=(dates[0], dates[-1]),
        metrics=tuple(metric_names),
        missing_count=missing_count,
        duplicate_count=duplicates,
        metric_summaries=summaries,
        trend_points=points,
    )


def build_default_dashboard(profile: DataProfile) -> DashboardSpec:
    def provenance(expression: str, fields: tuple[str, ...], rows: int = 1) -> QueryProvenance:
        return QueryProvenance(profile.snapshot_id, profile.sha256, expression, fields, rows)

    coverage = profile.date_range[0] if profile.date_range[0] == profile.date_range[1] else " → ".join(profile.date_range)
    quality_issues = profile.missing_count + profile.duplicate_count
    trend = profile.trend_points
    summary_rows = tuple(
        {
            "metric": metric,
            "count": summary.count,
            "minimum": summary.minimum,
            "maximum": summary.maximum,
            "average": summary.average,
        }
        for metric, summary in sorted(profile.metric_summaries.items())
    )
    blocks = (
        DashboardBlock("records", "kpi", "记录数", provenance("count rows", ("date",)), profile.row_count),
        DashboardBlock("metrics", "kpi", "指标数", provenance("count distinct metrics", ("metric",)), len(profile.metrics)),
        DashboardBlock("coverage", "kpi", "时间覆盖", provenance("minimum and maximum date", ("date",)), coverage),
        DashboardBlock("quality", "kpi", "质量问题", provenance("count missing cells and duplicate rows", ("date", "metric", "value")), quality_issues),
        DashboardBlock(
            "trend",
            "chart",
            "指标趋势",
            provenance("average value by date and metric, bounded to 1000 points", ("date", "metric", "value"), len(trend)),
            chart=FlintChartSpec(
                "line",
                {
                    "x": {"field": "date", "type": "temporal"},
                    "y": {"field": "value", "type": "quantitative"},
                    "color": {"field": "metric", "type": "nominal"},
                },
                ({"type": "aggregate", "op": "mean", "field": "value", "groupby": ["date", "metric"]},),
            ),
            data=trend,
        ),
        DashboardBlock(
            "distribution",
            "table",
            "指标分布",
            provenance("minimum maximum and average value by metric", ("metric", "value"), len(summary_rows)),
            data=summary_rows,
        ),
    )
    return DashboardSpec(f"dashboard-{profile.snapshot_id}", "数据概览", blocks)
