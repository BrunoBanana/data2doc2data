"""Deterministic, auditable business diagnostics over local derived series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from statistics import fmean, median, pstdev
from types import MappingProxyType
from typing import Mapping


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
