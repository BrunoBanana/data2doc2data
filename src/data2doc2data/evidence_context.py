"""Compact, server-owned evidence context for local agent conversations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .analysis import InsightResult, MAX_DOCUMENT_BYTES, read_metrics_source, resolve_sources
from .config import Profile
from .demo_scenarios import DemoScenarioCatalog
from .metrics import InputValidationError
from .retrieval import DocumentChunk, index_documents, search_chunks


DEFAULT_CONTEXT_BYTES = 24_000
MAX_CONTEXT_EXCERPTS = 5

# Bump this whenever the evidence envelope or ContextSummary schema changes in
# a way that a cross-harness consumer (WorkBuddy/DeepSeek harness/Codex plugin)
# must be aware of. The value is stamped into every envelope and summary.
CONTRACT_VERSION = 1


@dataclass(frozen=True)
class SourceProfile:
    fingerprint: str
    mode: str
    label: str
    synthetic: bool
    record_count: int
    metrics: tuple[str, ...]
    observation_dates: tuple[str, ...]
    document_count: int
    source_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MetricSummary:
    metric: str
    observation_count: int
    start_date: str
    end_date: str
    first_value: float
    last_value: float
    absolute_change: float


@dataclass(frozen=True)
class ContextSummary:
    snapshot_id: str
    source_fingerprint: str
    record_count: int
    metric_count: int
    date_count: int
    document_count: int
    excerpt_count: int
    compressed: bool
    contract_version: int = CONTRACT_VERSION

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSnapshot:
    summary: ContextSummary
    source: SourceProfile
    metrics: tuple[MetricSummary, ...]
    excerpts: tuple[DocumentChunk, ...]
    envelope: str
    analysis: InsightResult | None = None

    def render_prompt(self, message: str) -> str:
        return f"{self.envelope}\n\nUSER MESSAGE\n{message.strip()}"


class EvidenceContextBuilder:
    def __init__(self, max_context_bytes: int = DEFAULT_CONTEXT_BYTES) -> None:
        if max_context_bytes < 512:
            raise ValueError("context byte budget must be at least 512")
        self.max_context_bytes = max_context_bytes

    def build(
        self,
        question: str,
        profile: Profile,
        analysis: InsightResult | None = None,
        analysis_source_fingerprint: str | None = None,
        cache_path: Path | None = None,
    ) -> EvidenceSnapshot:
        normalized_question = question.strip()
        if not normalized_question:
            raise InputValidationError("agent question is required")
        source = build_source_profile(profile)
        csv_path, document_paths = resolve_sources(profile)
        rows, _ = read_metrics_source(csv_path)
        metrics = _metric_summaries(rows)
        ranked = search_chunks(
            normalized_question,
            index_documents(document_paths, cache_path),
            limit=MAX_CONTEXT_EXCERPTS,
        )
        matching_analysis = (
            analysis
            if analysis is not None and analysis_source_fingerprint == source.fingerprint
            else None
        )
        authoritative = _authoritative_context(source, metrics, matching_analysis)
        envelope = f"EVIDENCE CONTRACT v{CONTRACT_VERSION}\n{authoritative}"
        boundary = (
            "\n\nBOUNDARY\n"
            "These are locally computed facts. Agent explanations cannot replace deterministic validation. "
            "Do not claim access to raw CSV rows that are not included here."
        )
        if _byte_size(envelope + boundary) > self.max_context_bytes:
            raise InputValidationError("authoritative evidence exceeds the agent context budget")
        included = []
        for chunk in ranked:
            candidate = envelope + _format_excerpt(chunk) + boundary
            if _byte_size(candidate) > self.max_context_bytes:
                break
            included.append(chunk)
            envelope += _format_excerpt(chunk)
        compressed = len(included) < len(ranked)
        envelope += boundary
        snapshot_id = _snapshot_id(source, normalized_question, matching_analysis, included, compressed)
        summary = ContextSummary(
            snapshot_id=snapshot_id,
            source_fingerprint=source.fingerprint,
            record_count=source.record_count,
            metric_count=len(source.metrics),
            date_count=len(source.observation_dates),
            document_count=source.document_count,
            excerpt_count=len(included),
            compressed=compressed,
            contract_version=CONTRACT_VERSION,
        )
        return EvidenceSnapshot(summary, source, metrics, tuple(included), envelope, matching_analysis)


def build_source_profile(profile: Profile) -> SourceProfile:
    csv_path, document_paths = resolve_sources(profile)
    rows, csv_digest = read_metrics_source(csv_path)
    document_digests = tuple(_document_digest(path) for path in document_paths)
    source_hashes = (csv_digest, *document_digests)
    identity = {
        "mode": profile.mode,
        "paths": [str(csv_path.resolve()), *(str(path.resolve()) for path in document_paths)],
        "hashes": source_hashes,
    }
    fingerprint = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if profile.mode == "demo":
        label = DemoScenarioCatalog.load().get(profile.demo_scenario).label
    else:
        label = csv_path.name
    return SourceProfile(
        fingerprint=fingerprint,
        mode=profile.mode,
        label=label,
        synthetic=profile.mode == "demo",
        record_count=len(rows),
        metrics=tuple(sorted({row.metric for row in rows})),
        observation_dates=tuple(sorted({row.date.isoformat() for row in rows})),
        document_count=len(document_paths),
        source_hashes=source_hashes,
    )


def _metric_summaries(rows) -> tuple[MetricSummary, ...]:
    summaries = []
    for metric in sorted({row.metric for row in rows}):
        observations = sorted(
            (row for row in rows if row.metric == metric),
            key=lambda row: (row.date, row.source_row or 0),
        )
        first = observations[0]
        last = observations[-1]
        summaries.append(
            MetricSummary(
                metric=metric,
                observation_count=len(observations),
                start_date=first.date.isoformat(),
                end_date=last.date.isoformat(),
                first_value=first.value,
                last_value=last.value,
                absolute_change=last.value - first.value,
            )
        )
    return tuple(summaries)


def _authoritative_context(
    source: SourceProfile,
    metrics: tuple[MetricSummary, ...],
    analysis: InsightResult | None,
) -> str:
    source_lines = [
        "LOCAL FACTS",
        f"数据源: {source.label}",
        f"数据模式: {source.mode}",
        f"虚构合成数据: {'是' if source.synthetic else '否'}",
        f"记录数: {source.record_count}",
        f"指标数: {len(source.metrics)}",
        f"日期数: {len(source.observation_dates)}",
        f"日期范围: {source.observation_dates[0]} 至 {source.observation_dates[-1]}",
        f"文档数: {source.document_count}",
        f"指标: {', '.join(source.metrics)}",
        f"来源指纹: {source.fingerprint}",
        "",
        "LOCAL METRIC SUMMARIES",
    ]
    for item in metrics:
        source_lines.append(
            f"- {item.metric}: {item.observation_count} observations; "
            f"{item.start_date} to {item.end_date}; first={item.first_value:g}; "
            f"last={item.last_value:g}; change={item.absolute_change:g}"
        )
    if analysis is not None:
        payload = analysis.to_dict()
        findings = {
            "analysis_id": payload["provenance"]["analysis_id"],
            "question": payload["question"],
            "signal": payload["signal"],
            "context": payload["context"],
            "validation": payload["validation"],
            "verification": payload["verification"],
            "limitation": payload["limitation"],
        }
        source_lines.extend(
            [
                "",
                "DETERMINISTIC FINDINGS",
                json.dumps(findings, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ]
        )
    return "\n".join(source_lines)


def _format_excerpt(chunk: DocumentChunk) -> str:
    return (
        "\n\nDOCUMENT EXCERPT\n"
        f"source={chunk.path}; sha256={chunk.sha256}; "
        f"lines={chunk.start_line}-{chunk.end_line}; relevance={chunk.score:.4f}\n"
        f"{chunk.text}"
    )


def _snapshot_id(
    source: SourceProfile,
    question: str,
    analysis: InsightResult | None,
    excerpts: list[DocumentChunk],
    compressed: bool,
) -> str:
    payload = {
        "source": source.fingerprint,
        "question": question,
        "analysis": analysis.provenance.analysis_id if analysis is not None else None,
        "excerpts": [
            (chunk.sha256, chunk.start_line, chunk.end_line)
            for chunk in excerpts
        ],
        "compressed": compressed,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _byte_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _document_digest(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise InputValidationError(f"document is too large: {path.name}")
        content = path.read_bytes()
    except OSError as error:
        raise InputValidationError(f"cannot read document: {error}") from error
    if len(content) > MAX_DOCUMENT_BYTES:
        raise InputValidationError(f"document is too large: {path.name}")
    return hashlib.sha256(content).hexdigest()
