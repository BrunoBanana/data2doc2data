"""Bounded deterministic tools exposed to Demo and connected Agent Flow runners."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from .data_profile import profile_standard_csv
from .analytical_table import load_analytical_table
from .documents import build_document_corpus
from .hypotheses import validate_hypothesis_payload, verify_hypothesis
from .metrics import MetricRow
from .source_resolver import SourceResolver
from .text_dashboard import build_text_dashboard


@dataclass(frozen=True)
class ToolResult:
    tool: str
    status: str
    summary: Mapping[str, object]
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))


class LocalAnalysisTools:
    def __init__(self, allowed_roots: Iterable[Path] = ()) -> None:
        self.resolver = SourceResolver(allowed_roots)

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


def _load_metric_rows(path: Path) -> list[MetricRow]:
    table = load_analytical_table(path, "local-tool")
    return [MetricRow(row.date, row.metric, row.value, row.source_row) for row in table.rows]
