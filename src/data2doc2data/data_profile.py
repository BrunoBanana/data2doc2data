"""Model-free profiling and default dashboard planning for standard metric CSV snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from .analytical_table import AnalyticalTableError, load_analytical_table
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
    dimensions: tuple[str, ...]
    missing_count: int
    duplicate_count: int
    metric_summaries: dict[str, MetricSummary]
    trend_points: tuple[dict[str, object], ...]


def profile_standard_csv(path: Path, snapshot_id: str) -> DataProfile:
    try:
        table = load_analytical_table(path, snapshot_id)
    except AnalyticalTableError as exc:
        raise DataProfileError(str(exc)) from exc

    duplicates = len(table.rows) - len(
        {
            (row.date, row.metric, row.value, tuple(row.dimensions.items()))
            for row in table.rows
        }
    )
    dates = sorted({row.date.isoformat() for row in table.rows})
    metric_names = sorted({row.metric for row in table.rows})
    summaries = {}
    for metric in metric_names:
        values = [row.value for row in table.rows if row.metric == metric]
        summaries[metric] = MetricSummary(len(values), min(values), max(values), fmean(values))
    aggregates: dict[tuple[str, str], list[float]] = {}
    for row in table.rows:
        aggregates.setdefault((row.date.isoformat(), row.metric), []).append(row.value)
    points = tuple(
        {"date": item_date, "metric": metric, "value": fmean(values)}
        for (item_date, metric), values in sorted(aggregates.items())[:1000]
    )
    return DataProfile(
        snapshot_id=snapshot_id,
        sha256=table.sha256,
        row_count=table.source_row_count,
        field_count=len(table.fields),
        date_range=(dates[0], dates[-1]),
        metrics=tuple(metric_names),
        dimensions=table.dimensions,
        missing_count=table.missing_required_count,
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
