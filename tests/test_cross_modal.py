from data2doc2data.cross_modal import (
    compare_topics_with_metrics,
    find_explanatory_segments,
    test_text_metric_lag as analyze_text_metric_lag,
)
from data2doc2data.diagnostics import AnalyticalArtifact


def artifact(artifact_id: str, series: list[tuple[str, float]]) -> AnalyticalArtifact:
    return AnalyticalArtifact(
        artifact_id,
        "fixture_series",
        "completed",
        "fixture",
        {"series": [{"period": period, "value": value} for period, value in series]},
        len(series),
        {},
        source_refs=(artifact_id,),
    )


def test_topic_metric_alignment_uses_shared_periods_and_cites_artifacts():
    topic = artifact("topic-artifact", [(f"2026-{month:02d}", float(month)) for month in range(1, 11)])
    metric = artifact("metric-artifact", [(f"2026-{month:02d}", float(month * 2)) for month in range(2, 12)])

    result = compare_topics_with_metrics(topic, metric)

    assert result.status == "completed"
    assert result.observations["overlap"] == 9
    assert result.observations["correlation"] > 0.99
    assert result.source_refs == ("topic-artifact", "metric-artifact")
    assert any("因果" in item for item in result.limitations)


def test_text_metric_lag_finds_leading_text_signal_without_causal_claim():
    topic = artifact("topic", [(f"p{index}", value) for index, value in enumerate([1, 2, 4, 3, 6, 5, 8])])
    metric = artifact("metric", [(f"p{index}", value) for index, value in enumerate([0, 1, 2, 4, 3, 6, 5])])

    result = analyze_text_metric_lag(topic, metric, max_lag=2)

    assert result.observations["best_lag"] == 1
    assert result.observations["correlation"] > 0.99
    assert "候选" in result.summary
    assert any("因果" in item for item in result.limitations)


def test_cross_modal_tools_report_unavailable_for_missing_periods():
    topic = AnalyticalArtifact("topic", "fixture", "completed", "fixture", {}, 0, {})
    metric = artifact("metric", [("2026-01", 1), ("2026-02", 2)])

    result = compare_topics_with_metrics(topic, metric)

    assert result.status == "unavailable"
    assert result.source_refs == ("topic", "metric")


def test_explanatory_segments_are_ranked_as_hypotheses():
    relationship = AnalyticalArtifact(
        "relationship",
        "topic_metric_alignment",
        "completed",
        "aligned",
        {"correlation": 0.8, "overlap": 8},
        8,
        {},
    )
    segments = AnalyticalArtifact(
        "segments",
        "segment_rank",
        "completed",
        "ranked",
        {"by_change": [{"member": "直播", "delta": 30}, {"member": "货架", "delta": 10}]},
        20,
        {"dimension": "channel"},
    )

    result = find_explanatory_segments(relationship, segments)

    assert result.observations["hypotheses"][0]["member"] == "直播"
    assert result.observations["hypotheses"][0]["status"] == "hypothesis"
    assert any("因果" in item for item in result.limitations)
