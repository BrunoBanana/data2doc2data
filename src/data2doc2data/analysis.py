"""Deterministic, local-only evidence-loop analysis."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date
import hashlib
import io
import math
from pathlib import Path
import re

from .config import Profile
from .demo_scenarios import DemoScenarioCatalog, DemoScenarioError
from .hypotheses import ClauseVerification, parse_controlled_hypothesis, verify_hypothesis
from .metrics import InputValidationError, MetricRow, Signal, SignalEngine
from .provenance import AnalysisProvenance, SourceRef, build_provenance
from .retrieval import index_documents, search_chunks
from .rules import RuleSet, default_ruleset, load_ruleset


MAX_CSV_BYTES = 5_000_000
MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 200


@dataclass(frozen=True)
class DocumentContext:
    source: str
    excerpt: str
    relevance: float
    sha256: str = ""
    start_line: int | None = None
    end_line: int | None = None


@dataclass(frozen=True)
class Validation:
    status: str
    summary: str


@dataclass(frozen=True)
class Verification:
    status: str
    metric: str | None
    summary: str
    clauses: tuple[ClauseVerification, ...] = ()
    rule_id: str | None = None
    rule_name: str | None = None


@dataclass(frozen=True)
class InsightResult:
    question: str
    signal: Signal
    context: DocumentContext
    validation: Validation
    verification: Verification
    evidence: tuple[str, ...]
    provenance: AnalysisProvenance
    limitation: str

    def to_dict(self) -> dict[str, object]:
        return _serialize(asdict(self))


def _serialize(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def analyze(
    question: str,
    profile: Profile,
    metric_override: str | None = None,
    cache_path: Path | None = None,
    ruleset: RuleSet | None = None,
) -> InsightResult:
    normalized_question = question.strip()
    if not normalized_question:
        raise InputValidationError("question is required")
    if metric_override is not None and not isinstance(metric_override, str):
        raise InputValidationError("metric override must be text")
    contract = ruleset or default_ruleset()

    csv_path, document_paths = _resolve_sources(profile)
    rows, csv_sha256 = _read_metrics_source(csv_path)
    metric = _select_metric(normalized_question, rows, metric_override, contract.aliases())
    signal = _build_signal(metric, [row for row in rows if row.metric == metric], contract)
    context_query = f"{normalized_question} {metric} {' '.join(contract.aliases().get(metric, ()))}"
    context = _best_context(context_query, document_paths, cache_path)
    verification = _verify_document_condition(signal, rows, context, contract)
    validation = _validate(signal, context, verification)
    evidence = [
        f"指标来源：{csv_path}",
        f"文档来源：{context.source}",
    ]
    if verification.metric:
        evidence.append(f"验证指标：{verification.summary}")
    limitation = (
        "本地分析将 CSV 趋势与关键词匹配的文本进行对照。"
        "因果结论仍需补充数据并经人工复核。"
    )
    sources = (
        SourceRef(
            path=str(csv_path.resolve()),
            sha256=csv_sha256,
            rows=tuple(row.source_row for row in rows if row.source_row is not None),
        ),
        SourceRef(
            path=context.source,
            sha256=context.sha256,
            start_line=context.start_line,
            end_line=context.end_line,
        ),
    )
    provenance = build_provenance(
        sources,
        {
            "question": normalized_question,
            "metric": metric,
            "metric_override": metric_override,
            "signal_spec": asdict(signal.spec) if signal.spec else None,
        },
    )
    return InsightResult(
        question=normalized_question,
        signal=signal,
        context=context,
        validation=validation,
        verification=verification,
        evidence=tuple(evidence),
        provenance=provenance,
        limitation=limitation,
    )


def validate_profile(profile: Profile) -> None:
    """Validate configured local paths without storing or transmitting their contents."""
    csv_path, document_paths = _resolve_sources(profile)
    _read_metrics(csv_path)
    _best_context("evidence", document_paths)
    if profile.rules_path:
        load_ruleset(Path(profile.rules_path))


def load_profile_ruleset(profile: Profile) -> RuleSet | None:
    """Load the declarative rules contract attached to a profile, if any."""
    if not profile.rules_path:
        return None
    return load_ruleset(Path(profile.rules_path))


def resolve_sources(profile: Profile) -> tuple[Path, list[Path]]:
    """Resolve and validate the fixed evidence sources for a saved profile."""
    return _resolve_sources(profile)


def read_metrics_source(csv_path: Path) -> tuple[list[MetricRow], str]:
    """Read a bounded metrics source and return parsed rows plus its digest."""
    return _read_metrics_source(csv_path)


def _resolve_sources(profile: Profile) -> tuple[Path, list[Path]]:
    if profile.mode == "demo":
        try:
            metrics_path, document_path = DemoScenarioCatalog.load().sources(profile.demo_scenario)
        except DemoScenarioError as error:
            raise InputValidationError(f"cannot load demo scenario: {error}") from error
        return metrics_path, [document_path]

    csv_path = Path(profile.data_path).expanduser()
    if not csv_path.is_file():
        raise InputValidationError("CSV file does not exist")
    if not profile.knowledge_path.strip():
        return csv_path, []
    document_root = Path(profile.knowledge_path).expanduser()
    if not document_root.is_dir():
        raise InputValidationError("document directory does not exist")
    document_paths = sorted(
        path for path in document_root.rglob("*") if path.suffix.lower() in {".md", ".txt"}
    )
    if not document_paths:
        raise InputValidationError("document directory must contain .md or .txt files")
    if len(document_paths) > MAX_DOCUMENTS:
        raise InputValidationError(f"document directory has too many files; limit is {MAX_DOCUMENTS}")
    return csv_path, document_paths


def _read_metrics(csv_path: Path) -> list[MetricRow]:
    rows, _ = _read_metrics_source(csv_path)
    return rows


def _read_metrics_source(csv_path: Path) -> tuple[list[MetricRow], str]:
    try:
        if csv_path.stat().st_size > MAX_CSV_BYTES:
            raise InputValidationError(f"CSV is too large; limit is {MAX_CSV_BYTES} bytes")
        content = csv_path.read_bytes()
        if len(content) > MAX_CSV_BYTES:
            raise InputValidationError(f"CSV is too large; limit is {MAX_CSV_BYTES} bytes")
        digest = hashlib.sha256(content).hexdigest()
        with io.StringIO(content.decode("utf-8"), newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "metric", "value"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise InputValidationError("CSV must include date, metric, value columns")
            rows = []
            for source_row, record in enumerate(reader, start=2):
                value = float(record["value"])
                if not math.isfinite(value):
                    raise InputValidationError("CSV metric values must be finite numbers")
                rows.append(
                    MetricRow(
                        date=date.fromisoformat(record["date"].strip()),
                        metric=record["metric"].strip().lower(),
                        value=value,
                        source_row=source_row,
                    )
                )
    except (OSError, ValueError, csv.Error) as error:
        if isinstance(error, InputValidationError):
            raise
        raise InputValidationError(f"cannot read CSV: {error}") from error
    if not rows:
        raise InputValidationError("CSV has no metric rows")
    return rows, digest


def _select_metric(
    question: str,
    rows: list[MetricRow],
    metric_override: str | None = None,
    aliases: dict[str, tuple[str, ...]] | None = None,
) -> str:
    metrics = sorted({row.metric for row in rows})
    metrics_by_normalized_name = {_normalize_metric(metric): metric for metric in metrics}
    alias_map = aliases or {}

    if metric_override and metric_override.strip():
        requested_metric = metrics_by_normalized_name.get(_normalize_metric(metric_override))
        if requested_metric:
            return requested_metric
        available = ", ".join(metrics)
        raise InputValidationError(
            f"Metric '{metric_override.strip()}' is not available. Available metrics: {available}."
        )

    normalized_question = _normalize_metric(question)
    candidates = {
        metric
        for metric in metrics
        if _normalize_metric(metric) in normalized_question
        or any(
            _normalize_metric(alias) in normalized_question
            for alias in alias_map.get(metric, ())
        )
    }
    if len(candidates) == 1:
        return candidates.pop()
    if len(candidates) > 1:
        choices = ", ".join(sorted(candidates))
        raise InputValidationError(
            f"More than one metric matches the question: {choices}. Specify --metric <metric>."
        )
    raise InputValidationError("Unable to identify a metric. Specify --metric <metric>.")


def _build_signal(metric: str, rows: list[MetricRow], contract: RuleSet) -> Signal:
    return SignalEngine().build(contract.spec_for(metric), rows)


def _best_context(
    question: str,
    document_paths: list[Path],
    cache_path: Path | None = None,
) -> DocumentContext:
    chunks = index_documents(document_paths, cache_path, MAX_DOCUMENT_BYTES)
    if not chunks:
        raise InputValidationError("documents contain no readable text")
    ranked = search_chunks(question, chunks, limit=1)
    best = ranked[0] if ranked else chunks[0]
    return DocumentContext(
        str(best.path),
        best.text[:600],
        best.score,
        best.sha256,
        best.start_line,
        best.end_line,
    )


def _validate(
    signal: Signal,
    context: DocumentContext,
    verification: Verification | None = None,
) -> Validation:
    if context.relevance == 0:
        return Validation("insufficient", "所选文档与已确定指标没有相关交集。")
    if verification and verification.status == "confirmed":
        return Validation("supported", "文档中的条件同时符合两项本地指标变化，获得数据支持。")
    if verification and verification.status == "not_confirmed":
        return Validation("contradicted", "本地指标方向与文档中的策略假设相矛盾。")
    if verification and verification.status == "unavailable":
        return Validation("insufficient", "文档中的跨指标假设缺少可验证的本地指标。")
    context_tokens = set(_tokens(context.excerpt))
    metric_tokens = set(_tokens(signal.metric))
    has_metric_context = bool(metric_tokens.intersection(context_tokens))
    if signal.direction != "flat" and has_metric_context:
        return Validation("mixed", "文档与指标相关，但现有本地输入不足以建立因果解释。")
    return Validation("insufficient", "所选文档与测得信号的相关程度有限。")


def _verify_document_condition(
    primary_signal: Signal,
    rows: list[MetricRow],
    context: DocumentContext,
    contract: RuleSet,
) -> Verification:
    hypothesis = parse_controlled_hypothesis(context.excerpt, contract.aliases())
    if hypothesis is None or len(hypothesis.clauses) < 2:
        return Verification("not_applicable", None, "文档语境中未发现可验证的跨指标条件。")
    rule = contract.match_rule(hypothesis)
    target = rule.hypothesis() if rule else hypothesis
    specs = {clause.metric: contract.spec_for(clause.metric) for clause in target.clauses}
    result = verify_hypothesis(target, rows, specs)
    secondary_clause = next(
        (clause for clause in result.clauses if clause.metric != primary_signal.metric),
        result.clauses[0],
    )
    status = "not_confirmed" if result.status == "contradicted" else result.status
    display_name = contract.display_name(secondary_clause.metric)
    summary = f"{display_name}：{result.summary}"
    if rule:
        summary = f"规则「{rule.name}」：{summary}"
    return Verification(
        status,
        secondary_clause.metric,
        summary,
        result.clauses,
        rule.rule_id if rule else None,
        rule.name if rule else None,
    )


def _tokens(value: str) -> list[str]:
    normalized = value.lower().replace("_", " ")
    return re.findall(r"[a-z0-9]+", normalized) + re.findall(r"[\u4e00-\u9fff]", normalized)


def _normalize_metric(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)
