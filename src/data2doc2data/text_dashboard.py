"""Deterministic text dashboard derived from a provenance-backed corpus."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re

from .documents import DocumentCorpus


TOPIC_TERMS = ("收入", "留存", "激活", "转化", "成本", "利润", "增长", "风险", "目标", "策略")


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
            for line in section.text.splitlines():
                match = re.match(r"^\s*主张[：:]\s*(.+?)\s*$", line)
                if not match:
                    continue
                text = match.group(1)
                claim_id = "claim-" + hashlib.sha256(
                    f"{corpus.corpus_id}\0{document.sha256}\0{section.start_line}\0{text}".encode("utf-8")
                ).hexdigest()[:24]
                citation = TextCitation(
                    document.name,
                    document.sha256,
                    section.start_line,
                    section.end_line,
                    line.strip()[:500],
                )
                claims.append(DocumentClaim(claim_id, text, "pending", citation))
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
