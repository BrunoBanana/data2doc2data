"""Deterministic text dashboard derived from a provenance-backed corpus."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re

from .documents import DocumentCorpus


TOPIC_TERMS = ("收入", "留存", "激活", "转化", "成本", "利润", "增长", "风险", "目标", "策略")
METRIC_ALIASES = {
    "refund_rate": ("退款率", "退款比例", "refund_rate"),
    "retention_rate": ("留存率", "留存", "retention_rate"),
    "conversion_rate": ("转化率", "转化", "conversion_rate"),
    "activation_rate": ("激活率", "激活", "activation_rate"),
    "late_delivery_rate": ("延迟交付率", "延迟率", "late_delivery_rate"),
    "repeat_purchase_rate": ("复购率", "复购", "repeat_purchase_rate"),
    "gross_margin_rate": ("毛利率", "gross_margin_rate"),
    "revenue": ("收入", "营收", "revenue"),
    "gmv": ("成交额", "交易额", "gmv"),
    "orders": ("订单量", "订单数", "orders"),
}
UP_TERMS = ("明显上升", "显著上升", "上升", "上涨", "提高", "增加", "增长", "改善")
DOWN_TERMS = ("明显下降", "显著下降", "下降", "下跌", "降低", "减少", "恶化")
NEGATION_TERMS = ("并未", "没有", "未见", "并非", "不再", "未")
TIME_PATTERN = re.compile(
    r"(?:20\d{2}[-年/](?:1[0-2]|0?[1-9])月?|(?:1[0-2]|0?[1-9]|十[一二]?|[一二三四五六七八九])月)"
)


@dataclass(frozen=True)
class TextCitation:
    document: str
    sha256: str
    start_line: int
    end_line: int
    excerpt: str


@dataclass(frozen=True)
class DocumentClaim:
    claim_id: str
    text: str
    status: str
    citation: TextCitation
    conflicts_with: tuple[str, ...] = ()
    metric_refs: tuple[str, ...] = ()
    direction: str = "unknown"
    time_refs: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    negated: bool = False


@dataclass(frozen=True)
class TextDashboard:
    corpus_id: str
    document_count: int
    failure_count: int
    duplicate_count: int
    topics: tuple[str, ...]
    entities: tuple[str, ...]
    claims: tuple[DocumentClaim, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "corpus_id": self.corpus_id,
            "document_count": self.document_count,
            "failure_count": self.failure_count,
            "duplicate_count": self.duplicate_count,
            "topics": list(self.topics),
            "entities": list(self.entities),
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "status": claim.status,
                    "citation": {
                        "document": claim.citation.document,
                        "sha256": claim.citation.sha256,
                        "start_line": claim.citation.start_line,
                        "end_line": claim.citation.end_line,
                        "excerpt": claim.citation.excerpt,
                    },
                    "conflicts_with": list(claim.conflicts_with),
                    "metric_refs": list(claim.metric_refs),
                    "direction": claim.direction,
                    "time_refs": list(claim.time_refs),
                    "entities": list(claim.entities),
                    "negated": claim.negated,
                }
                for claim in self.claims
            ],
        }


def build_text_dashboard(corpus: DocumentCorpus) -> TextDashboard:
    full_text = "\n".join(section.text for document in corpus.documents for section in document.sections)
    topics = tuple(term for term in TOPIC_TERMS if term in full_text)[:20]
    regions = set(re.findall(r"(?:华东|华南|华北|华中|西南|西北|东北)区", full_text))
    latin = set(re.findall(r"\b[A-Z][A-Za-z0-9_-]{1,31}\b", full_text))
    entities = tuple(sorted(regions | latin))[:50]
    claims: list[DocumentClaim] = []
    for document in corpus.documents:
        for section in document.sections:
            for line_offset, line in enumerate(section.text.splitlines()):
                explicit = re.match(r"^\s*主张[：:]\s*(.+?)\s*$", line)
                text = explicit.group(1) if explicit else line.strip()
                structured = _structured_claim(text)
                if not explicit and (not structured[0] or structured[1] == "unknown"):
                    continue
                claim_id = "claim-" + hashlib.sha256(
                    f"{corpus.corpus_id}\0{document.sha256}\0{section.start_line + line_offset}\0{text}".encode("utf-8")
                ).hexdigest()[:24]
                citation = TextCitation(
                    document.name,
                    document.sha256,
                    section.start_line + line_offset,
                    section.start_line + line_offset,
                    line.strip()[:500],
                )
                metric_refs, direction, time_refs, claim_entities, negated = structured
                claims.append(
                    DocumentClaim(
                        claim_id,
                        text,
                        "pending",
                        citation,
                        metric_refs=metric_refs,
                        direction=direction,
                        time_refs=time_refs,
                        entities=claim_entities,
                        negated=negated,
                    )
                )
    signatures = [_claim_signature(claim.text) for claim in claims]
    linked = []
    for index, claim in enumerate(claims):
        conflicts = tuple(
            other.claim_id
            for other_index, other in enumerate(claims)
            if other_index != index and signatures[other_index] == signatures[index] and other.text != claim.text
        )
        linked.append(replace(claim, conflicts_with=conflicts))
    return TextDashboard(
        corpus.corpus_id,
        len(corpus.documents),
        len(corpus.failures),
        corpus.duplicate_count,
        topics,
        entities,
        tuple(linked[:200]),
    )


def _claim_signature(text: str) -> str:
    return re.sub(r"\s+|[0-9]+(?:\.[0-9]+)?", "", text).lower()


def _structured_claim(text: str) -> tuple[tuple[str, ...], str, tuple[str, ...], tuple[str, ...], bool]:
    lowered = text.lower()
    matches: list[tuple[int, str]] = []
    for metric, aliases in METRIC_ALIASES.items():
        positions = [lowered.find(alias.lower()) for alias in aliases if alias.lower() in lowered]
        if positions:
            matches.append((min(positions), metric))
    metric_refs = tuple(metric for _, metric in sorted(matches))
    negated = any(term in text for term in NEGATION_TERMS)
    has_up = any(term in text for term in UP_TERMS)
    has_down = any(term in text for term in DOWN_TERMS)
    if negated or has_up == has_down:
        direction = "ambiguous" if negated or has_up or has_down else "unknown"
    else:
        direction = "up" if has_up else "down"
    time_refs = tuple(dict.fromkeys(match.group(0) for match in TIME_PATTERN.finditer(text)))[:20]
    regions = re.findall(r"(?:华东|华南|华北|华中|西南|西北|东北)区?", text)
    channels = [term for term in ("直播", "货架", "自然", "付费", "企业", "中小客户") if term in text]
    entities = tuple(dict.fromkeys(regions + channels))[:20]
    return metric_refs, direction, time_refs, entities, negated
