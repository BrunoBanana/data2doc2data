"""Deterministic, auditable business diagnostics over local derived series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import random
from statistics import fmean, median, pstdev, variance
from types import MappingProxyType
from typing import Mapping

from .analytical_table import AnalyticalRow, AnalyticalTable


@dataclass(frozen=True)
class SeriesPoint:
    date: date
    value: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.value):
            raise ValueError("series values must be finite")


@dataclass(frozen=True)
class AnalyticalArtifact:
    artifact_id: str
    method: str
    status: str
    summary: str
    observations: Mapping[str, object]
    sample_size: int
    parameters: Mapping[str, object]
    diagnostics: tuple[Mapping[str, object], ...] = ()
    limitations: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "observations", MappingProxyType(dict(self.observations)))
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(
            self,
            "diagnostics",
            tuple(MappingProxyType(dict(item)) for item in self.diagnostics),
        )


def compare_periods(
    points: tuple[SeriesPoint, ...],
    *,
    split: int | None = None,
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    ordered = _ordered(points)
    boundary = split if split is not None else len(ordered) // 2
    if len(ordered) < 2 or boundary < 1 or boundary >= len(ordered):
        return _unavailable(
            "compare_periods",
            len(ordered),
            {"split": split},
            "周期比较至少需要两个观测值和两个非空窗口。",
            source_refs,
        )
    baseline = fmean(point.value for point in ordered[:boundary])
    current = fmean(point.value for point in ordered[boundary:])
    absolute_change = current - baseline
    diagnostics: tuple[Mapping[str, object], ...] = ()
    if baseline == 0:
        change_percent = None
        diagnostics = ({"code": "zero_baseline", "message": "基准值为零，相对变化不适用。"},)
    else:
        change_percent = (absolute_change / abs(baseline)) * 100
    observations = {
        "baseline": baseline,
        "current": current,
        "absolute_change": absolute_change,
        "change_percent": change_percent,
        "baseline_count": boundary,
        "current_count": len(ordered) - boundary,
        "baseline_range": [ordered[0].date.isoformat(), ordered[boundary - 1].date.isoformat()],
        "current_range": [ordered[boundary].date.isoformat(), ordered[-1].date.isoformat()],
    }
    parameters = {"method": "two_window_mean", "split": boundary}
    return _artifact(
        "compare_periods",
        "completed",
        "已完成基准期与当前期的本地比较。",
        observations,
        len(ordered),
        parameters,
        diagnostics=diagnostics,
        limitations=("周期比较描述时间关联，不单独证明变化原因。",),
        source_refs=source_refs,
    )


def detect_anomalies(
    points: tuple[SeriesPoint, ...],
    *,
    window: int = 5,
    threshold: float = 6.0,
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    ordered = _ordered(points)
    if window < 3 or not math.isfinite(threshold) or threshold <= 0:
        raise ValueError("anomaly window and threshold are invalid")
    if len(ordered) <= window:
        return _unavailable(
            "detect_anomalies",
            len(ordered),
            {"window": window, "threshold": threshold},
            f"稳健异常检测至少需要 {window + 1} 个观测值。",
            source_refs,
        )

    anomalies = []
    for index in range(window, len(ordered)):
        history = [point.value for point in ordered[index - window : index]]
        center = median(history)
        deviations = [abs(value - center) for value in history]
        mad = median(deviations)
        scale = max(1.4826 * mad, fmean(deviations), 1e-12)
        score = abs(ordered[index].value - center) / scale
        if score > threshold:
            anomalies.append(
                {
                    "index": index,
                    "date": ordered[index].date.isoformat(),
                    "value": ordered[index].value,
                    "local_median": center,
                    "robust_score": score,
                }
            )
    observations = {"anomalies": anomalies, "anomaly_count": len(anomalies)}
    parameters = {"method": "rolling_median_mad", "window": window, "threshold": threshold}
    return _artifact(
        "detect_anomalies",
        "completed",
        f"检测到 {len(anomalies)} 个稳健异常点。",
        observations,
        len(ordered),
        parameters,
        limitations=("异常表示偏离局部基线，不等同于业务故障或因果解释。",),
        source_refs=source_refs,
    )


def detect_change_points(
    points: tuple[SeriesPoint, ...],
    *,
    minimum_window: int = 4,
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    ordered = _ordered(points)
    if minimum_window < 2:
        raise ValueError("minimum window must be at least two")
    if len(ordered) < minimum_window * 2:
        return _unavailable(
            "detect_change_points",
            len(ordered),
            {"minimum_window": minimum_window},
            f"变化点检测至少需要 {minimum_window * 2} 个观测值。",
            source_refs,
        )
    values = [point.value for point in ordered]
    spread = pstdev(values)
    if spread == 0:
        return _unavailable(
            "detect_change_points",
            len(ordered),
            {"minimum_window": minimum_window},
            "常量序列没有可识别的结构变化点。",
            source_refs,
        )

    candidates = []
    for index in range(minimum_window, len(ordered) - minimum_window + 1):
        before = fmean(values[:index])
        after = fmean(values[index:])
        delta = after - before
        balance = math.sqrt(index * (len(ordered) - index) / len(ordered))
        candidates.append((abs(delta) * balance, index, before, after, delta))
    _, index, before, after, delta = max(candidates, key=lambda item: (item[0], -item[1]))
    effect_size = abs(delta) / spread
    observations = {
        "change_index": index,
        "change_date": ordered[index].date.isoformat(),
        "before_mean": before,
        "after_mean": after,
        "absolute_change": delta,
        "effect_size": effect_size,
        "before_count": index,
        "after_count": len(ordered) - index,
    }
    parameters = {"method": "bounded_mean_shift", "minimum_window": minimum_window}
    return _artifact(
        "detect_change_points",
        "completed",
        f"最强候选结构变化发生在 {ordered[index].date.isoformat()}。",
        observations,
        len(ordered),
        parameters,
        limitations=("变化点是水平漂移候选，需要结合业务事件与更多周期复核。",),
        source_refs=source_refs,
    )


def segment_rank(
    table: AnalyticalTable,
    *,
    metric: str,
    dimension: str,
    split_date: date | None = None,
    minimum_samples: int = 1,
) -> AnalyticalArtifact:
    rows = tuple(row for row in table.rows if row.metric == metric)
    parameters = {
        "method": "segment_window_rank",
        "metric": metric,
        "dimension": dimension,
        "split_date": split_date.isoformat() if split_date else None,
        "minimum_samples": minimum_samples,
    }
    limitation = _dimension_limitation(table, rows, dimension, minimum_samples)
    if limitation:
        return _unavailable("segment_rank", len(rows), parameters, limitation, (table.snapshot_id,))
    boundary = split_date or _middle_date(rows)
    members = _member_windows(rows, dimension, boundary)
    ranked = [
        {
            "member": member,
            "baseline": sum(values[0]),
            "current": sum(values[1]),
            "delta": sum(values[1]) - sum(values[0]),
            "baseline_count": len(values[0]),
            "current_count": len(values[1]),
        }
        for member, values in members.items()
        if len(values[0]) >= minimum_samples and len(values[1]) >= minimum_samples
    ]
    if not ranked:
        return _unavailable(
            "segment_rank",
            len(rows),
            parameters,
            "没有分组同时满足基准期、当前期和最小样本要求。",
            (table.snapshot_id,),
        )
    observations = {
        "by_current": sorted(ranked, key=lambda item: (-float(item["current"]), str(item["member"]))),
        "by_change": sorted(ranked, key=lambda item: (-float(item["delta"]), str(item["member"]))),
    }
    return _artifact(
        "segment_rank",
        "completed",
        f"已按 {dimension} 对 {len(ranked)} 个分组完成排名。",
        observations,
        len(rows),
        parameters,
        limitations=("分组排名描述当前输入中的差异，不自动解释差异原因。",),
        source_refs=(table.snapshot_id,),
    )


def decompose_change(
    table: AnalyticalTable,
    *,
    metric: str,
    dimension: str,
    split_date: date | None = None,
    numerator_metric: str | None = None,
    denominator_metric: str | None = None,
) -> AnalyticalArtifact:
    parameters = {
        "method": "additive_change_decomposition",
        "metric": metric,
        "dimension": dimension,
        "split_date": split_date.isoformat() if split_date else None,
        "numerator_metric": numerator_metric,
        "denominator_metric": denominator_metric,
    }
    if dimension not in table.dimensions:
        return _unavailable(
            "decompose_change",
            0,
            parameters,
            f"数据中不存在维度 {dimension}。",
            (table.snapshot_id,),
        )
    if _is_rate_metric(metric):
        if not numerator_metric or not denominator_metric:
            return _unavailable(
                "decompose_change",
                0,
                parameters,
                "比率指标贡献分解需要明确的分子指标和分母指标。",
                (table.snapshot_id,),
            )
        return _decompose_rate(
            table,
            metric,
            dimension,
            numerator_metric,
            denominator_metric,
            split_date,
            parameters,
        )

    rows = tuple(row for row in table.rows if row.metric == metric)
    limitation = _dimension_limitation(table, rows, dimension, 1)
    if limitation:
        return _unavailable("decompose_change", len(rows), parameters, limitation, (table.snapshot_id,))
    boundary = split_date or _middle_date(rows)
    members = _member_windows(rows, dimension, boundary)
    contributors = []
    for member, (baseline_values, current_values) in members.items():
        delta = sum(current_values) - sum(baseline_values)
        contributors.append(
            {
                "member": member,
                "baseline": sum(baseline_values),
                "current": sum(current_values),
                "delta": delta,
            }
        )
    total_delta = sum(float(item["delta"]) for item in contributors)
    for item in contributors:
        item["contribution_percent"] = None if total_delta == 0 else float(item["delta"]) / total_delta * 100
    contributors.sort(key=lambda item: (-abs(float(item["delta"])), str(item["member"])))
    return _artifact(
        "decompose_change",
        "completed",
        f"已将 {metric} 的变化拆解到 {dimension}。",
        {"total_delta": total_delta, "contributors": contributors},
        len(rows),
        parameters,
        limitations=("加法贡献表示总体变化的数值构成，不单独证明驱动机制。",),
        source_refs=(table.snapshot_id,),
    )


def correlate_metrics(
    leading: tuple[SeriesPoint, ...],
    lagging: tuple[SeriesPoint, ...],
    *,
    max_lag: int = 3,
    minimum_overlap: int = 3,
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    if max_lag < 0 or max_lag > 30:
        raise ValueError("maximum lag must be between zero and thirty")
    if minimum_overlap < 3:
        raise ValueError("minimum overlap must be at least three")
    leading_by_date = {point.date: point.value for point in _ordered(leading)}
    lagging_by_date = {point.date: point.value for point in _ordered(lagging)}
    shared_dates = sorted(set(leading_by_date) & set(lagging_by_date))
    x = [leading_by_date[item_date] for item_date in shared_dates]
    y = [lagging_by_date[item_date] for item_date in shared_dates]
    parameters = {
        "method": "bounded_lag_pearson",
        "max_lag": max_lag,
        "minimum_overlap": minimum_overlap,
        "positive_lag_meaning": "leading series precedes lagging series",
    }
    if len(shared_dates) < minimum_overlap:
        return _unavailable(
            "correlate_metrics",
            len(shared_dates),
            parameters,
            "两个指标没有足够的重叠日期。",
            source_refs,
        )
    lag_results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            left, right = x[-lag:], y[: len(y) + lag]
        elif lag > 0:
            left, right = x[: len(x) - lag], y[lag:]
        else:
            left, right = x, y
        if len(left) < minimum_overlap:
            continue
        coefficient = _pearson(left, right)
        if coefficient is None:
            continue
        lag_results.append({"lag": lag, "correlation": coefficient, "overlap": len(left)})
    if not lag_results:
        return _unavailable(
            "correlate_metrics",
            len(shared_dates),
            parameters,
            "指标方差或有效重叠不足，无法计算相关性。",
            source_refs,
        )
    best = max(
        lag_results,
        key=lambda item: (
            abs(float(item["correlation"])),
            int(item["overlap"]),
            -abs(int(item["lag"])),
            -int(item["lag"]),
        ),
    )
    observations = {
        "best_lag": best["lag"],
        "correlation": best["correlation"],
        "overlap": best["overlap"],
        "lag_results": lag_results,
    }
    return _artifact(
        "correlate_metrics",
        "completed",
        f"最强时间关联出现在滞后 {best['lag']} 个观测周期。",
        observations,
        len(shared_dates),
        parameters,
        limitations=(
            "相关与滞后只描述时间关联，不代表因果关系。",
            "缺失日期、共同趋势和季节性可能抬高相关系数。",
        ),
        source_refs=source_refs,
    )


def compare_groups(
    first: list[float],
    second: list[float],
    *,
    confidence: float = 0.95,
    bootstrap_samples: int = 2_000,
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    if not 0.8 <= confidence < 1:
        raise ValueError("confidence must be between 0.8 and 1")
    if not 100 <= bootstrap_samples <= 20_000:
        raise ValueError("bootstrap sample count must be between 100 and 20000")
    if any(not math.isfinite(value) for value in (*first, *second)):
        raise ValueError("group values must be finite")
    seed = _stable_seed(first, second, confidence, bootstrap_samples)
    parameters = {
        "method": "pooled_effect_deterministic_bootstrap",
        "confidence": confidence,
        "bootstrap_samples": bootstrap_samples,
        "seed": seed,
    }
    if len(first) < 2 or len(second) < 2:
        return _unavailable(
            "compare_groups",
            len(first) + len(second),
            parameters,
            "组间比较要求每组至少两个观测值。",
            source_refs,
        )
    first_mean, second_mean = fmean(first), fmean(second)
    difference = first_mean - second_mean
    pooled_variance = (
        (len(first) - 1) * variance(first) + (len(second) - 1) * variance(second)
    ) / (len(first) + len(second) - 2)
    diagnostics: tuple[Mapping[str, object], ...] = ()
    if pooled_variance == 0:
        effect_size = None
        diagnostics = ({"code": "zero_within_group_variance", "message": "组内方差为零，标准化效应量不适用。"},)
    else:
        effect_size = abs(difference) / math.sqrt(pooled_variance)
    rng = random.Random(seed)
    bootstrap = sorted(
        fmean(rng.choice(first) for _ in first) - fmean(rng.choice(second) for _ in second)
        for _ in range(bootstrap_samples)
    )
    tail = (1 - confidence) / 2
    lower = _quantile(bootstrap, tail)
    upper = _quantile(bootstrap, 1 - tail)
    observations = {
        "first_mean": first_mean,
        "second_mean": second_mean,
        "difference": difference,
        "effect_size": effect_size,
        "confidence_interval": [lower, upper],
        "first_count": len(first),
        "second_count": len(second),
    }
    return _artifact(
        "compare_groups",
        "completed",
        "已完成组间差异、标准化效应量和确定性自助法区间计算。",
        observations,
        len(first) + len(second),
        parameters,
        diagnostics=diagnostics,
        limitations=(
            "区间反映当前样本的不确定性，依赖观测独立且分组口径可比。",
            "观察性组间差异不代表因果效应。",
        ),
        source_refs=source_refs,
    )


def _pearson(first: list[float], second: list[float]) -> float | None:
    first_mean, second_mean = fmean(first), fmean(second)
    first_centered = [value - first_mean for value in first]
    second_centered = [value - second_mean for value in second]
    denominator = math.sqrt(
        sum(value * value for value in first_centered)
        * sum(value * value for value in second_centered)
    )
    if denominator == 0:
        return None
    return sum(left * right for left, right in zip(first_centered, second_centered, strict=True)) / denominator


def _stable_seed(first: list[float], second: list[float], confidence: float, samples: int) -> int:
    encoded = json.dumps([first, second, confidence, samples], separators=(",", ":"), allow_nan=False)
    return int(hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16], 16)


def _quantile(values: list[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _decompose_rate(
    table: AnalyticalTable,
    metric: str,
    dimension: str,
    numerator_metric: str,
    denominator_metric: str,
    split_date: date | None,
    parameters: Mapping[str, object],
) -> AnalyticalArtifact:
    rows = tuple(row for row in table.rows if row.metric in {numerator_metric, denominator_metric})
    if not rows:
        return _unavailable(
            "decompose_change",
            0,
            parameters,
            "比率分子或分母指标没有可用数据。",
            (table.snapshot_id,),
        )
    boundary = split_date or _middle_date(rows)
    by_metric = {
        name: _member_windows(tuple(row for row in rows if row.metric == name), dimension, boundary)
        for name in (numerator_metric, denominator_metric)
    }
    members = sorted(set(by_metric[numerator_metric]) | set(by_metric[denominator_metric]))
    values = []
    for member in members:
        numerator = by_metric[numerator_metric].get(member, ([], []))
        denominator = by_metric[denominator_metric].get(member, ([], []))
        n0, n1 = sum(numerator[0]), sum(numerator[1])
        d0, d1 = sum(denominator[0]), sum(denominator[1])
        if d0 <= 0 or d1 <= 0:
            continue
        values.append({"member": member, "n0": n0, "n1": n1, "d0": d0, "d1": d1})
    total_d0 = sum(item["d0"] for item in values)
    total_d1 = sum(item["d1"] for item in values)
    if not values or total_d0 <= 0 or total_d1 <= 0:
        return _unavailable(
            "decompose_change",
            len(rows),
            parameters,
            "比率分解要求每个周期存在正的分母。",
            (table.snapshot_id,),
        )
    contributors = []
    for item in values:
        w0, w1 = item["d0"] / total_d0, item["d1"] / total_d1
        r0, r1 = item["n0"] / item["d0"], item["n1"] / item["d1"]
        within = (w0 + w1) / 2 * (r1 - r0)
        mix = (r0 + r1) / 2 * (w1 - w0)
        contributors.append(
            {"member": item["member"], "within": within, "mix": mix, "delta": within + mix}
        )
    baseline_rate = sum(item["n0"] for item in values) / total_d0
    current_rate = sum(item["n1"] for item in values) / total_d1
    total_delta = current_rate - baseline_rate
    contributors.sort(key=lambda item: (-abs(float(item["delta"])), str(item["member"])))
    return _artifact(
        "decompose_change",
        "completed",
        f"已使用分子/分母口径拆解 {metric} 的变化。",
        {
            "baseline": baseline_rate,
            "current": current_rate,
            "total_delta": total_delta,
            "contributors": contributors,
        },
        len(rows),
        {**parameters, "method": "symmetric_rate_decomposition"},
        limitations=("比率贡献分为组内变化与结构占比变化，不单独证明因果。",),
        source_refs=(table.snapshot_id,),
    )


def _dimension_limitation(
    table: AnalyticalTable,
    rows: tuple[AnalyticalRow, ...],
    dimension: str,
    minimum_samples: int,
) -> str | None:
    if dimension not in table.dimensions:
        return f"数据中不存在维度 {dimension}。"
    if not rows:
        return "指定指标没有可用数据。"
    if minimum_samples < 1:
        raise ValueError("minimum samples must be positive")
    if len({row.date for row in rows}) < 2:
        return "维度分析至少需要两个日期。"
    return None


def _middle_date(rows: tuple[AnalyticalRow, ...]) -> date:
    dates = sorted({row.date for row in rows})
    return dates[len(dates) // 2]


def _member_windows(
    rows: tuple[AnalyticalRow, ...],
    dimension: str,
    boundary: date,
) -> dict[str, tuple[list[float], list[float]]]:
    members: dict[str, tuple[list[float], list[float]]] = {}
    for row in rows:
        member = row.dimensions.get(dimension) or "（未标注）"
        baseline, current = members.setdefault(member, ([], []))
        (baseline if row.date < boundary else current).append(row.value)
    return members


def _is_rate_metric(metric: str) -> bool:
    normalized = metric.lower()
    return normalized.endswith("率") or any(
        token in normalized
        for token in ("rate", "ratio", "margin", "retention", "conversion", "churn", "refund", "return")
    )


def _ordered(points: tuple[SeriesPoint, ...]) -> tuple[SeriesPoint, ...]:
    return tuple(sorted(points, key=lambda point: point.date))


def _unavailable(
    method: str,
    sample_size: int,
    parameters: Mapping[str, object],
    limitation: str,
    source_refs: tuple[str, ...],
) -> AnalyticalArtifact:
    return _artifact(
        method,
        "unavailable",
        "当前输入不足以完成该计算。",
        {},
        sample_size,
        parameters,
        limitations=(limitation,),
        source_refs=source_refs,
    )


def _artifact(
    method: str,
    status: str,
    summary: str,
    observations: Mapping[str, object],
    sample_size: int,
    parameters: Mapping[str, object],
    *,
    diagnostics: tuple[Mapping[str, object], ...] = (),
    limitations: tuple[str, ...] = (),
    source_refs: tuple[str, ...] = (),
) -> AnalyticalArtifact:
    identity = json.dumps(
        {
            "method": method,
            "status": status,
            "observations": observations,
            "sample_size": sample_size,
            "parameters": parameters,
            "source_refs": source_refs,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    artifact_id = f"artifact-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
    return AnalyticalArtifact(
        artifact_id,
        method,
        status,
        summary,
        observations,
        sample_size,
        parameters,
        diagnostics,
        limitations,
        source_refs,
    )
