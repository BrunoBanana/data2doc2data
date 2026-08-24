"""Bounded deterministic tools exposed to Demo and connected Agent Flow runners."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
from statistics import fmean
from types import MappingProxyType
from typing import Iterable, Mapping

from .analytical_table import load_analytical_table
from .artifacts import ArtifactStore
from .cross_modal import compare_topics_with_metrics, find_explanatory_segments, test_text_metric_lag
from .data_profile import profile_standard_csv
from .diagnostics import (
    AnalyticalArtifact,
    SeriesPoint,
    compare_groups,
    compare_periods,
    correlate_metrics,
    decompose_change,
    detect_anomalies,
    detect_change_points,
    segment_rank,
)
from .documents import build_document_corpus
from .hypotheses import validate_hypothesis_payload, verify_hypothesis
from .metrics import MetricRow
from .semantic_text import LocalSentenceTransformerAdapter, semantic_cluster
from .source_resolver import SourceResolver
from .text_dashboard import build_text_dashboard
from .text_ml import TextMLResult, analyze_text_corpus, build_word_cloud_svg


BASE_ANALYSIS_TOOLS = frozenset(
    {"inspect_sources", "profile_data", "query_data", "extract_claims", "align_evidence", "test_hypothesis"}
)
DEEP_ANALYSIS_TOOLS = frozenset(
    {
        "compare_periods",
        "detect_anomalies",
        "detect_change_points",
        "segment_rank",
        "decompose_change",
        "correlate_metrics",
        "compare_groups",
        "analyze_text",
        "semantic_cluster",
        "compare_topics_with_metrics",
        "test_text_metric_lag",
        "find_explanatory_segments",
    }
)
REGISTERED_ANALYSIS_TOOLS = BASE_ANALYSIS_TOOLS | DEEP_ANALYSIS_TOOLS


@dataclass(frozen=True)
class ToolResult:
    tool: str
    status: str
    summary: Mapping[str, object]
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))

    def agent_projection(self, max_bytes: int = 8_192) -> dict[str, object]:
        """Return a path-free, raw-row-free envelope suitable for a planner."""
        if max_bytes < 512 or max_bytes > 32_768:
            raise ValueError("agent projection size must be between 512 and 32768 bytes")
        projection = {
            "tool": self.tool,
            "status": self.status,
            "summary": _compact_agent_value(self.summary),
            "artifact_refs": list(self.artifact_refs[:50]),
        }
        encoded = json.dumps(projection, ensure_ascii=False, sort_keys=True).encode("utf-8")
        if len(encoded) <= max_bytes:
            return projection
        return {
            "tool": self.tool,
            "status": self.status,
            "summary": {"truncated": True},
            "artifact_refs": list(self.artifact_refs[:20]),
        }


class LocalAnalysisTools:
    def __init__(self, allowed_roots: Iterable[Path] = (), *, artifact_store: ArtifactStore | None = None) -> None:
        self.resolver = SourceResolver(allowed_roots)
        self.artifact_store = artifact_store

    def inspect_sources(self, paths: Iterable[Path]) -> ToolResult:
        resolved = self.resolver.resolve(tuple(paths))
        return ToolResult(
            "inspect_sources",
            "completed",
            {
                "modalities": list(resolved.modalities),
                "dataset_count": len(resolved.datasets),
                "document_count": len(resolved.documents),
                "row_count": sum(dataset.row_count for dataset in resolved.datasets),
                "diagnostics": [
                    {"name": diagnostic.name, "message": diagnostic.message}
                    for diagnostic in resolved.diagnostics[:20]
                ],
            },
        )

    def profile_data(self, path: Path, snapshot_id: str) -> ToolResult:
        approved = self.resolver.approved_path(path)
        profile = profile_standard_csv(approved, snapshot_id)
        return ToolResult(
            "profile_data",
            "completed",
            {
                "row_count": profile.row_count,
                "metric_count": len(profile.metrics),
                "metrics": list(profile.metrics),
                "dimensions": list(profile.dimensions),
                "date_range": list(profile.date_range),
                "quality_issue_count": profile.missing_count + profile.duplicate_count,
            },
            (snapshot_id,),
        )

    def query_data(self, path: Path, snapshot_id: str, metric: str) -> ToolResult:
        approved = self.resolver.approved_path(path)
        profile = profile_standard_csv(approved, snapshot_id)
        summary = profile.metric_summaries.get(metric)
        if summary is None:
            return ToolResult(
                "query_data",
                "unavailable",
                {"metric": metric, "available_metrics": list(profile.metrics)},
                (snapshot_id,),
            )
        return ToolResult(
            "query_data",
            "completed",
            {
                "metric": metric,
                "count": summary.count,
                "minimum": summary.minimum,
                "maximum": summary.maximum,
                "average": summary.average,
            },
            (snapshot_id,),
        )

    def extract_claims(self, paths: Iterable[Path], corpus_id: str) -> ToolResult:
        approved = tuple(self.resolver.approved_path(path) for path in paths)
        dashboard = build_text_dashboard(build_document_corpus(approved, corpus_id))
        return ToolResult(
            "extract_claims",
            "completed",
            {
                "document_count": dashboard.document_count,
                "failure_count": dashboard.failure_count,
                "claim_count": len(dashboard.claims),
                "claims": [
                    {
                        "claim_id": claim.claim_id,
                        "status": claim.status,
                        "document": claim.citation.document,
                        "start_line": claim.citation.start_line,
                        "end_line": claim.citation.end_line,
                    }
                    for claim in dashboard.claims[:50]
                ],
            },
            (corpus_id,),
        )

    def align_evidence(
        self,
        data_path: Path,
        snapshot_id: str,
        document_paths: Iterable[Path],
        corpus_id: str,
    ) -> ToolResult:
        approved_data = self.resolver.approved_path(data_path)
        approved_documents = tuple(self.resolver.approved_path(path) for path in document_paths)
        profile = profile_standard_csv(approved_data, snapshot_id)
        dashboard = build_text_dashboard(build_document_corpus(approved_documents, corpus_id))
        alignments = [
            {
                "claim_id": claim.claim_id,
                "metric": metric,
                "document": claim.citation.document,
            }
            for claim in dashboard.claims
            for metric in profile.metrics
            if metric.lower() in claim.text.lower()
        ][:100]
        return ToolResult(
            "align_evidence",
            "completed",
            {
                "alignment_count": len(alignments),
                "alignments": alignments,
                "unmatched_claim_count": max(0, len(dashboard.claims) - len({item["claim_id"] for item in alignments})),
            },
            (snapshot_id, corpus_id),
        )

    def test_hypothesis(self, path: Path, snapshot_id: str, payload: object) -> ToolResult:
        approved = self.resolver.approved_path(path)
        profile_standard_csv(approved, snapshot_id)
        hypothesis = validate_hypothesis_payload(payload)
        verification = verify_hypothesis(hypothesis, _load_metric_rows(approved))
        return ToolResult(
            "test_hypothesis",
            "completed",
            {
                "status": verification.status,
                "summary": verification.summary,
                "clauses": [
                    {
                        "metric": clause.metric,
                        "expected_direction": clause.expected_direction,
                        "observed_direction": clause.observed_direction,
                        "status": clause.status,
                    }
                    for clause in verification.clauses
                ],
            },
            (snapshot_id,),
        )

    def compare_periods(self, path: Path, snapshot_id: str, *, metric: str, split: int | None = None) -> ToolResult:
        table = self._table(path, snapshot_id)
        return self._analytical_result(compare_periods(_metric_series(table, metric), split=split, source_refs=(snapshot_id,)))

    def detect_anomalies(
        self,
        path: Path,
        snapshot_id: str,
        *,
        metric: str,
        window: int = 5,
        threshold: float = 6.0,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        artifact = detect_anomalies(
            _metric_series(table, metric),
            window=window,
            threshold=threshold,
            source_refs=(snapshot_id,),
        )
        return self._analytical_result(artifact)

    def detect_change_points(
        self,
        path: Path,
        snapshot_id: str,
        *,
        metric: str,
        minimum_window: int = 4,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        return self._analytical_result(
            detect_change_points(
                _metric_series(table, metric),
                minimum_window=minimum_window,
                source_refs=(snapshot_id,),
            )
        )

    def segment_rank(
        self,
        path: Path,
        snapshot_id: str,
        *,
        metric: str,
        dimension: str,
        split_date: str | None = None,
        minimum_samples: int = 1,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        return self._analytical_result(
            segment_rank(
                table,
                metric=metric,
                dimension=dimension,
                split_date=_optional_date(split_date),
                minimum_samples=minimum_samples,
            )
        )

    def decompose_change(
        self,
        path: Path,
        snapshot_id: str,
        *,
        metric: str,
        dimension: str,
        split_date: str | None = None,
        numerator_metric: str | None = None,
        denominator_metric: str | None = None,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        return self._analytical_result(
            decompose_change(
                table,
                metric=metric,
                dimension=dimension,
                split_date=_optional_date(split_date),
                numerator_metric=numerator_metric,
                denominator_metric=denominator_metric,
            )
        )

    def correlate_metrics(
        self,
        path: Path,
        snapshot_id: str,
        *,
        leading_metric: str,
        lagging_metric: str,
        max_lag: int = 3,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        return self._analytical_result(
            correlate_metrics(
                _metric_series(table, leading_metric),
                _metric_series(table, lagging_metric),
                max_lag=max_lag,
                source_refs=(snapshot_id,),
            )
        )

    def compare_groups(
        self,
        path: Path,
        snapshot_id: str,
        *,
        metric: str,
        dimension: str,
        first_group: str,
        second_group: str,
        bootstrap_samples: int = 2_000,
    ) -> ToolResult:
        table = self._table(path, snapshot_id)
        if dimension not in table.dimensions:
            raise ValueError(f"data does not contain dimension {dimension}")
        first = [row.value for row in table.rows if row.metric == metric and row.dimensions.get(dimension) == first_group]
        second = [row.value for row in table.rows if row.metric == metric and row.dimensions.get(dimension) == second_group]
        return self._analytical_result(
            compare_groups(first, second, bootstrap_samples=bootstrap_samples, source_refs=(snapshot_id,))
        )

    def analyze_text(self, paths: Iterable[Path], corpus_id: str, *, seed: int = 7) -> ToolResult:
        approved = tuple(self.resolver.approved_path(path) for path in paths)
        result = analyze_text_corpus(build_document_corpus(approved, corpus_id), seed=seed)
        return self._text_result(result)

    def semantic_cluster(
        self,
        paths: Iterable[Path],
        corpus_id: str,
        *,
        model_path: str,
        seed: int = 7,
    ) -> ToolResult:
        approved = tuple(self.resolver.approved_path(path) for path in paths)
        adapter = LocalSentenceTransformerAdapter(self.resolver.approved_path(Path(model_path)))
        result = semantic_cluster(build_document_corpus(approved, corpus_id), adapter=adapter, seed=seed)
        return self._text_result(result)

    def compare_topics_with_metrics(self, topic_ref: str, metric_ref: str) -> ToolResult:
        return self._cross_modal_result(compare_topics_with_metrics(self._artifact(topic_ref), self._artifact(metric_ref)))

    def test_text_metric_lag(self, topic_ref: str, metric_ref: str, *, max_lag: int = 3) -> ToolResult:
        return self._cross_modal_result(
            test_text_metric_lag(self._artifact(topic_ref), self._artifact(metric_ref), max_lag=max_lag)
        )

    def find_explanatory_segments(self, relationship_ref: str, segment_ref: str) -> ToolResult:
        return self._cross_modal_result(
            find_explanatory_segments(self._artifact(relationship_ref), self._artifact(segment_ref))
        )

    def _table(self, path: Path, snapshot_id: str):
        return load_analytical_table(self.resolver.approved_path(path), snapshot_id)

    def _artifact(self, artifact_ref: str) -> AnalyticalArtifact:
        if self.artifact_store is None:
            raise ValueError("artifact store is required for cross-modal tools")
        return self.artifact_store.load_analytical(artifact_ref)

    def _analytical_result(self, artifact: AnalyticalArtifact) -> ToolResult:
        if self.artifact_store is not None:
            self.artifact_store.save_analytical(artifact)
        observations = dict(artifact.observations)
        summary = {
            "method": artifact.method,
            "summary": artifact.summary,
            "sample_size": artifact.sample_size,
            "observations": observations,
            "limitations": list(artifact.limitations),
        }
        return ToolResult(artifact.method, artifact.status, summary, (artifact.artifact_id,))

    def _cross_modal_result(self, artifact: AnalyticalArtifact) -> ToolResult:
        return self._analytical_result(artifact)

    def _text_result(self, result: TextMLResult) -> ToolResult:
        payload = _text_payload(result)
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24]
        artifact_id = f"artifact-text-{digest}"
        payload["word_cloud_svg"] = build_word_cloud_svg(result.keyword_weights, seed=result.seed)
        if self.artifact_store is not None:
            self.artifact_store.save(artifact_id, "text_ml", payload)
        return ToolResult(
            "analyze_text" if result.method != "local_embeddings" else "semantic_cluster",
            result.status,
            {
                "method": result.method,
                "topic_count": len(result.topics),
                "cluster_count": len(result.clusters),
                "topics": [
                    {"topic_id": topic.topic_id, "label": topic.label, "keywords": list(topic.keywords[:10])}
                    for topic in result.topics[:12]
                ],
                "diagnostics": [dict(item) for item in result.diagnostics[:20]],
            },
            (artifact_id,),
        )


def _load_metric_rows(path: Path) -> list[MetricRow]:
    table = load_analytical_table(path, "local-tool")
    return [MetricRow(row.date, row.metric, row.value, row.source_row) for row in table.rows]


def _metric_series(table, metric: str) -> tuple[SeriesPoint, ...]:
    grouped: dict[date, list[float]] = {}
    for row in table.rows:
        if row.metric == metric:
            grouped.setdefault(row.date, []).append(row.value)
    return tuple(SeriesPoint(item_date, fmean(values)) for item_date, values in sorted(grouped.items()))


def _optional_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("split_date must use ISO YYYY-MM-DD") from exc


def _compact_agent_value(value: object) -> object:
    if isinstance(value, Mapping):
        forbidden = {"row", "rows", "raw", "raw_data", "records", "path", "paths"}
        return {
            str(key): _compact_agent_value(item)
            for key, item in value.items()
            if str(key).lower() not in forbidden
        }
    if isinstance(value, (list, tuple)):
        return [_compact_agent_value(item) for item in value[:100]]
    if isinstance(value, str):
        if value.startswith(("/", "~/")) or ":\\" in value:
            return "[local reference omitted]"
        return value[:1_000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)[:500]


def _text_payload(result: TextMLResult) -> dict[str, object]:
    return {
        "corpus_id": result.corpus_id,
        "status": result.status,
        "method": result.method,
        "seed": result.seed,
        "model_versions": dict(result.model_versions),
        "keyword_weights": dict(result.keyword_weights),
        "topics": [
            {
                "topic_id": topic.topic_id,
                "label": topic.label,
                "keywords": list(topic.keywords),
                "weight": topic.weight,
                "representatives": [
                    {
                        "text": representative.text,
                        "score": representative.score,
                        "citation": {
                            "document": representative.citation.document,
                            "sha256": representative.citation.sha256,
                            "start_line": representative.citation.start_line,
                            "end_line": representative.citation.end_line,
                        },
                    }
                    for representative in topic.representatives
                ],
            }
            for topic in result.topics
        ],
        "clusters": [
            {
                "cluster_id": cluster.cluster_id,
                "label": cluster.label,
                "keywords": list(cluster.keywords),
                "documents": list(cluster.documents),
            }
            for cluster in result.clusters
        ],
        "outliers": list(result.outliers),
        "diagnostics": [dict(item) for item in result.diagnostics],
    }
