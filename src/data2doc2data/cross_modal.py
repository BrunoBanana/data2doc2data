"""Deterministic alignment between derived text signals and metric artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from statistics import fmean

from .diagnostics import AnalyticalArtifact


def compare_topics_with_metrics(
    topic_artifact: AnalyticalArtifact,
    metric_artifact: AnalyticalArtifact,
    *,
    minimum_overlap: int = 3,
) -> AnalyticalArtifact:
    """Compare aligned topic and metric signals without making a causal claim."""
    topic, metric, periods = _aligned(topic_artifact, metric_artifact)
    parameters = {"method": "aligned_pearson", "minimum_overlap": minimum_overlap}
    refs = (topic_artifact.artifact_id, metric_artifact.artifact_id)
    if len(periods) < minimum_overlap:
        return _unavailable("topic_metric_alignment", refs, parameters, len(periods), "共享周期不足，无法交叉比较。")
    correlation = _pearson(topic, metric)
    if correlation is None:
        return _unavailable("topic_metric_alignment", refs, parameters, len(periods), "序列方差不足，无法计算关联。")
    return _artifact(
        "topic_metric_alignment",
        refs,
        parameters,
        len(periods),
        f"文本主题与指标在 {len(periods)} 个共享周期内完成关联比较。",
        {"overlap": len(periods), "periods": periods, "correlation": correlation},
        ("时间对齐与相关性只用于提出待验证假设，不代表因果关系。",),
    )


def test_text_metric_lag(
    topic_artifact: AnalyticalArtifact,
    metric_artifact: AnalyticalArtifact,
    *,
    max_lag: int = 3,
    minimum_overlap: int = 3,
) -> AnalyticalArtifact:
    """Search a bounded lag window for a text-leading metric candidate."""
    if max_lag < 0 or max_lag > 30:
        raise ValueError("maximum lag must be between zero and thirty")
    topic, metric, periods = _aligned(topic_artifact, metric_artifact)
    refs = (topic_artifact.artifact_id, metric_artifact.artifact_id)
    parameters = {
        "method": "bounded_text_metric_lag",
        "max_lag": max_lag,
        "minimum_overlap": minimum_overlap,
        "positive_lag_meaning": "text signal precedes metric signal",
    }
    candidates = []
    for lag in range(0, max_lag + 1):
        left = topic[: len(topic) - lag] if lag else topic
        right = metric[lag:] if lag else metric
        if len(left) < minimum_overlap:
            continue
        correlation = _pearson(left, right)
        if correlation is not None:
            candidates.append({"lag": lag, "correlation": correlation, "overlap": len(left)})
    if not candidates:
        return _unavailable("text_metric_lag", refs, parameters, len(periods), "有效重叠或序列方差不足。")
    best = max(candidates, key=lambda item: (abs(float(item["correlation"])), int(item["overlap"]), -int(item["lag"])))
    return _artifact(
        "text_metric_lag",
        refs,
        parameters,
        len(periods),
        f"识别到文本信号领先 {best['lag']} 个周期的关联候选。",
        {
            "best_lag": best["lag"],
            "correlation": best["correlation"],
            "overlap": best["overlap"],
            "lag_results": candidates,
        },
        ("领先关系是时间关联候选，不构成文本主题与指标之间的因果证明。",),
    )


def find_explanatory_segments(
    relationship_artifact: AnalyticalArtifact,
    segment_artifact: AnalyticalArtifact,
    *,
    limit: int = 10,
) -> AnalyticalArtifact:
    """Rank segment candidates behind a cross-modal relationship as hypotheses."""
    if limit < 1 or limit > 50:
        raise ValueError("segment hypothesis limit must be between one and fifty")
    refs = (relationship_artifact.artifact_id, segment_artifact.artifact_id)
    parameters = {"method": "cross_modal_segment_hypotheses", "limit": limit}
    ranked = segment_artifact.observations.get("by_change")
    correlation = relationship_artifact.observations.get("correlation")
    if not isinstance(ranked, list) or not isinstance(correlation, (int, float)):
        return _unavailable("explanatory_segments", refs, parameters, 0, "缺少关联或分组变化产物。")
    hypotheses = []
    for item in ranked[:limit]:
        if not isinstance(item, dict) or not isinstance(item.get("member"), str):
            continue
        delta = item.get("delta")
        if not isinstance(delta, (int, float)) or not math.isfinite(float(delta)):
            continue
        hypotheses.append(
            {
                "member": item["member"],
                "delta": float(delta),
                "score": abs(float(delta) * float(correlation)),
                "status": "hypothesis",
            }
        )
    hypotheses.sort(key=lambda item: (-float(item["score"]), str(item["member"])))
    if not hypotheses:
        return _unavailable("explanatory_segments", refs, parameters, 0, "没有有效的分组候选。")
    return _artifact(
        "explanatory_segments",
        refs,
        parameters,
        len(hypotheses),
        f"生成 {len(hypotheses)} 个需要继续验证的分组解释候选。",
        {"hypotheses": hypotheses, "dimension": segment_artifact.parameters.get("dimension")},
        ("候选排序结合相关强度与分组变化，不构成因果证明。",),
    )


def _aligned(
    first: AnalyticalArtifact,
    second: AnalyticalArtifact,
) -> tuple[list[float], list[float], list[str]]:
    first_values = _series(first)
    second_values = _series(second)
    periods = sorted(set(first_values) & set(second_values))
    return [first_values[item] for item in periods], [second_values[item] for item in periods], periods


def _series(artifact: AnalyticalArtifact) -> dict[str, float]:
    values: dict[str, float] = {}
    raw = artifact.observations.get("series")
    if not isinstance(raw, list):
        return values
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("period"), str):
            continue
        value = item.get("value")
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            values[item["period"]] = float(value)
    return values


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean, right_mean = fmean(left), fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_scale = math.sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = math.sqrt(sum((value - right_mean) ** 2 for value in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def _artifact(
    method: str,
    refs: tuple[str, str],
    parameters: dict[str, object],
    sample_size: int,
    summary: str,
    observations: dict[str, object],
    limitations: tuple[str, ...],
    status: str = "completed",
) -> AnalyticalArtifact:
    payload = json.dumps([method, refs, parameters, observations], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    artifact_id = f"artifact-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"
    return AnalyticalArtifact(
        artifact_id,
        method,
        status,
        summary,
        observations,
        sample_size,
        parameters,
        limitations=limitations,
        source_refs=refs,
    )


def _unavailable(
    method: str,
    refs: tuple[str, str],
    parameters: dict[str, object],
    sample_size: int,
    limitation: str,
) -> AnalyticalArtifact:
    return _artifact(method, refs, parameters, sample_size, limitation, {}, (limitation,), status="unavailable")
