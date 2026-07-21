"""Deterministic, local-only evidence-loop analysis."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import re

from .config import Profile


METRIC_ALIASES = {
    "retention_rate": ("retention", "retention rate", "留存", "留存率"),
    "activation_rate": ("activation", "activation rate", "激活", "激活率"),
}
METRIC_DISPLAY_NAMES = {
    "retention_rate": "留存率",
    "activation_rate": "激活率",
}
MAX_CSV_BYTES = 5_000_000
MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 200


class InputValidationError(ValueError):
    """Raised when local user-owned source files do not meet package requirements."""


@dataclass(frozen=True)
class MetricRow:
    date: date
    metric: str
    value: float


@dataclass(frozen=True)
class Signal:
    metric: str
    baseline: float
    current: float
    change_percent: float
    direction: str
    summary: str


@dataclass(frozen=True)
class DocumentContext:
    source: str
    excerpt: str
    relevance: int


@dataclass(frozen=True)
class Validation:
    status: str
    summary: str


@dataclass(frozen=True)
class Verification:
    status: str
    metric: str | None
    summary: str


@dataclass(frozen=True)
class InsightResult:
    question: str
    signal: Signal
    context: DocumentContext
    validation: Validation
    verification: Verification
    evidence: tuple[str, ...]
    limitation: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def analyze(
    question: str,
    profile: Profile,
    metric_override: str | None = None,
) -> InsightResult:
    normalized_question = question.strip()
    if not normalized_question:
        raise InputValidationError("question is required")
    if metric_override is not None and not isinstance(metric_override, str):
        raise InputValidationError("metric override must be text")

    csv_path, document_paths = _resolve_sources(profile)
    rows = _read_metrics(csv_path)
    metric = _select_metric(normalized_question, rows, metric_override)
    signal = _build_signal(metric, [row for row in rows if row.metric == metric])
    context_query = f"{normalized_question} {metric} {' '.join(METRIC_ALIASES.get(metric, ()))}"
    context = _best_context(context_query, document_paths)
    verification = _verify_document_condition(signal, rows, context)
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
    return InsightResult(normalized_question, signal, context, validation, verification, tuple(evidence), limitation)


def validate_profile(profile: Profile) -> None:
    """Validate configured local paths without storing or transmitting their contents."""
    csv_path, document_paths = _resolve_sources(profile)
    _read_metrics(csv_path)
    _best_context("evidence", document_paths)


def _resolve_sources(profile: Profile) -> tuple[Path, list[Path]]:
    if profile.mode == "demo":
        root = Path(__file__).resolve().parent / "sample"
        return root / "metrics.csv", [root / "strategy.md"]

    csv_path = Path(profile.data_path).expanduser()
    document_root = Path(profile.knowledge_path).expanduser()
    if not csv_path.is_file():
        raise InputValidationError("CSV file does not exist")
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
    try:
        if csv_path.stat().st_size > MAX_CSV_BYTES:
            raise InputValidationError(f"CSV is too large; limit is {MAX_CSV_BYTES} bytes")
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            required = {"date", "metric", "value"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise InputValidationError("CSV must include date, metric, value columns")
            rows = [
                MetricRow(
                    date=date.fromisoformat(record["date"].strip()),
                    metric=record["metric"].strip().lower(),
                    value=float(record["value"]),
                )
                for record in reader
            ]
    except (OSError, ValueError, csv.Error) as error:
        if isinstance(error, InputValidationError):
            raise
        raise InputValidationError(f"cannot read CSV: {error}") from error
    if not rows:
        raise InputValidationError("CSV has no metric rows")
    return rows


def _select_metric(
    question: str,
    rows: list[MetricRow],
    metric_override: str | None = None,
) -> str:
    metrics = sorted({row.metric for row in rows})
    metrics_by_normalized_name = {_normalize_metric(metric): metric for metric in metrics}

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
            for alias in METRIC_ALIASES.get(metric, ())
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


def _build_signal(metric: str, rows: list[MetricRow]) -> Signal:
    ordered_rows = sorted(rows, key=lambda row: row.date)
    if len(ordered_rows) < 2:
        raise InputValidationError(f"Metric '{metric}' needs at least two dated observations.")
    midpoint = max(1, len(ordered_rows) // 2)
    baseline = sum(row.value for row in ordered_rows[:midpoint]) / midpoint
    current_rows = ordered_rows[midpoint:]
    current = sum(row.value for row in current_rows) / len(current_rows)
    change_percent = 0.0 if baseline == 0 else ((current - baseline) / abs(baseline)) * 100
    direction = "up" if change_percent > 1 else "down" if change_percent < -1 else "flat"
    display_name = METRIC_DISPLAY_NAMES.get(metric, metric)
    direction_label = {"up": "上升", "down": "下降", "flat": "基本持平"}[direction]
    summary = f"{display_name}从 {baseline:.2f} 变为 {current:.2f}（{change_percent:+.1f}%），呈{direction_label}趋势。"
    return Signal(metric, baseline, current, change_percent, direction, summary)


def _best_context(question: str, document_paths: list[Path]) -> DocumentContext:
    question_tokens = set(_tokens(question))
    best: tuple[int, Path, str] | None = None
    for path in document_paths:
        try:
            size = path.stat().st_size
        except OSError as error:
            raise InputValidationError(f"cannot read document: {path}") from error
        if size > MAX_DOCUMENT_BYTES:
            raise InputValidationError(f"document is too large: {path.name}")
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            raise InputValidationError(f"cannot read document: {path}") from error
        for excerpt in _paragraphs(text):
            relevance = len(question_tokens.intersection(_tokens(excerpt)))
            candidate = (relevance, path, excerpt)
            if best is None or candidate[0] > best[0]:
                best = candidate
    if best is None:
        raise InputValidationError("documents contain no readable text")
    relevance, path, excerpt = best
    return DocumentContext(str(path), excerpt[:600], relevance)


def _validate(
    signal: Signal,
    context: DocumentContext,
    verification: Verification | None = None,
) -> Validation:
    if context.relevance == 0:
        return Validation("insufficient", "所选文档与已确定指标没有相关交集。")
    if verification and verification.status == "confirmed":
        return Validation("supported", "文档中的条件同时符合两项本地指标变化，获得数据支持。")
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
) -> Verification:
    context_tokens = set(_tokens(context.excerpt))
    expected_terms = {"activation", "rises", "retention", "falls"}
    chinese_expected_terms = set("激活上升留存下降")
    if (
        primary_signal.metric != "retention_rate"
        or primary_signal.direction != "down"
        or not (
            expected_terms.issubset(context_tokens)
            or chinese_expected_terms.issubset(context_tokens)
        )
    ):
        return Verification("not_applicable", None, "文档语境中未发现可验证的跨指标条件。")

    activation_rows = [row for row in rows if row.metric == "activation_rate"]
    if len(activation_rows) < 2:
        return Verification("unavailable", "activation_rate", "文档条件所需的激活率数据不可用。")
    activation_signal = _build_signal("activation_rate", activation_rows)
    if activation_signal.direction == "up":
        return Verification(
            "confirmed",
            "activation_rate",
            f"激活率从 {activation_signal.baseline:.2f} 上升至 {activation_signal.current:.2f}。",
        )
    return Verification(
        "not_confirmed",
        "activation_rate",
        f"激活率呈{ {'up': '上升', 'down': '下降', 'flat': '基本持平'}[activation_signal.direction] }趋势，与文档中的上升条件不一致。",
    )


def _tokens(value: str) -> list[str]:
    normalized = value.lower().replace("_", " ")
    return re.findall(r"[a-z0-9]+", normalized) + re.findall(r"[\u4e00-\u9fff]", normalized)


def _normalize_metric(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)


def _paragraphs(text: str) -> list[str]:
    paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n", text) if part.strip()]
    return paragraphs or [" ".join(text.split())]
