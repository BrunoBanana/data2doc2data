"""Deterministic, line-aware local document indexing and retrieval."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .metrics import InputValidationError


INDEX_VERSION = 1
DEFAULT_MAX_DOCUMENT_BYTES = 1_000_000

# Static, auditable synonym groups. Each group's first term is the canonical
# form; every other term normalizes to it before BM25 scoring. This is the only
# place cross-language business synonyms are defined, so retrieval stays fully
# deterministic and zero-dependency. Extend this table to widen recall; it never
# changes stored chunk text (chunks remain verbatim and traceable).
SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("客户", "用户", "customer", "user"),
    ("收入", "营收", "销售额", "营业额", "revenue"),
    ("流失", "流失率", "churn"),
    ("留存", "留存率", "retention"),
    ("激活", "激活率", "activation"),
    ("转化", "转化率", "conversion"),
    ("利润", "盈利", "profit", "margin"),
    ("成本", "费用", "cost", "expense"),
)


def build_synonym_map(groups: tuple[tuple[str, ...], ...]) -> dict[str, str]:
    """Flatten synonym groups into a term -> canonical lookup."""
    mapping: dict[str, str] = {}
    for group in groups:
        canonical = group[0].lower()
        for term in group:
            mapping[term.lower()] = canonical
    return mapping


DEFAULT_SYNONYMS = build_synonym_map(SYNONYM_GROUPS)


@dataclass(frozen=True)
class DocumentChunk:
    path: Path
    text: str
    start_line: int
    end_line: int
    sha256: str
    score: float = 0.0


def index_documents(
    paths: list[Path],
    cache_path: Path | None = None,
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES,
) -> list[DocumentChunk]:
    """Create paragraph chunks, optionally reusing a private content-validated cache."""
    cache = _load_cache(cache_path)
    cached_files = cache.get("files", {}) if isinstance(cache, dict) else {}
    next_files = {}
    chunks = []
    for requested_path in sorted(paths, key=lambda path: str(path.resolve())):
        path = requested_path.resolve()
        try:
            metadata = path.stat()
            if metadata.st_size > max_document_bytes:
                raise InputValidationError(f"document is too large: {path.name}")
            content = path.read_bytes()
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InputValidationError(f"document must be UTF-8 text: {path}") from error
        except OSError as error:
            raise InputValidationError(f"cannot read document: {path}") from error

        digest = hashlib.sha256(content).hexdigest()
        cache_key = str(path)
        cached = cached_files.get(cache_key, {}) if isinstance(cached_files, dict) else {}
        identity = {
            "size": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
            "sha256": digest,
        }
        document_chunks = _cached_chunks(path, cached, identity)
        if document_chunks is None:
            document_chunks = _chunk_document(path, text, digest)
        serialized_chunks = [
            {
                "text": chunk.text,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
            }
            for chunk in document_chunks
        ]
        next_files[cache_key] = {**identity, "chunks": serialized_chunks}
        chunks.extend(document_chunks)

    if cache_path is not None:
        _write_cache(cache_path, {"version": INDEX_VERSION, "files": next_files})
    return chunks


def search_chunks(
    query: str,
    chunks: list[DocumentChunk],
    limit: int = 5,
    minimum_relevance: float = 0.01,
    synonyms: dict[str, str] | None = DEFAULT_SYNONYMS,
) -> list[DocumentChunk]:
    """Rank chunks using normalized BM25 terms with deterministic tie-breaking.

    ``synonyms`` maps non-canonical terms to canonical forms before scoring,
    widening recall across equivalent business vocabulary (e.g. 客户/用户,
    营收/收入). Pass ``synonyms=None`` to disable normalization.
    """
    if not chunks or limit <= 0:
        return []
    query_terms = Counter(_terms(query, synonyms))
    if not query_terms:
        return []
    document_terms = [Counter(_terms(chunk.text, synonyms)) for chunk in chunks]
    lengths = [sum(terms.values()) for terms in document_terms]
    average_length = sum(lengths) / len(lengths) or 1.0
    document_frequency = {
        term: sum(term in terms for terms in document_terms)
        for term in query_terms
    }
    idf = {
        term: math.log(1 + (len(chunks) - frequency + 0.5) / (frequency + 0.5))
        for term, frequency in document_frequency.items()
    }
    k1 = 1.2
    b = 0.75
    maximum = sum(weight * (k1 + 1) * query_terms[term] for term, weight in idf.items()) or 1.0
    ranked = []
    for chunk, terms, length in zip(chunks, document_terms, lengths):
        score = 0.0
        for term, query_frequency in query_terms.items():
            frequency = terms.get(term, 0)
            if not frequency:
                continue
            denominator = frequency + k1 * (1 - b + b * length / average_length)
            score += idf[term] * (frequency * (k1 + 1) / denominator) * query_frequency
        normalized_score = min(1.0, score / maximum)
        if normalized_score >= minimum_relevance:
            ranked.append(replace(chunk, score=normalized_score))
    ranked.sort(key=lambda chunk: (-chunk.score, str(chunk.path), chunk.start_line))
    return ranked[:limit]


def _terms(value: str, synonyms: dict[str, str] | None = None) -> list[str]:
    normalized = value.lower().replace("_", " ")
    terms = re.findall(r"[a-z0-9]+", normalized)
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        terms.extend(run[index : index + 2] for index in range(max(0, len(run) - 1)))
        terms.extend(run[index : index + 3] for index in range(max(0, len(run) - 2)))
    if synonyms:
        terms = [synonyms.get(term, term) for term in terms]
    return terms


def _chunk_document(path: Path, text: str, digest: str) -> list[DocumentChunk]:
    chunks = []
    paragraph_lines = []
    start_line = 1
    lines = text.splitlines()
    for line_number, line in enumerate([*lines, ""], start=1):
        if line.strip():
            if not paragraph_lines:
                start_line = line_number
            paragraph_lines.append(line.strip())
            continue
        if paragraph_lines:
            chunks.append(
                DocumentChunk(
                    path,
                    " ".join(paragraph_lines),
                    start_line,
                    line_number - 1,
                    digest,
                )
            )
            paragraph_lines = []
    return chunks


def _cached_chunks(path: Path, cached: object, identity: dict[str, object]) -> list[DocumentChunk] | None:
    if not isinstance(cached, dict) or any(cached.get(key) != value for key, value in identity.items()):
        return None
    raw_chunks = cached.get("chunks")
    if not isinstance(raw_chunks, list):
        return None
    chunks = []
    for item in raw_chunks:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            return None
        try:
            start_line = int(item["start_line"])
            end_line = int(item["end_line"])
        except (KeyError, TypeError, ValueError):
            return None
        if start_line < 1 or end_line < start_line:
            return None
        chunks.append(
            DocumentChunk(
                path,
                item["text"],
                start_line,
                end_line,
                str(identity["sha256"]),
            )
        )
    return chunks


def _load_cache(cache_path: Path | None) -> object:
    if cache_path is None or not cache_path.is_file():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != INDEX_VERSION:
        return {}
    return payload


def _write_cache(cache_path: Path, payload: dict[str, object]) -> None:
    cache_path = cache_path.expanduser()
    cache_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=cache_path.parent,
            prefix=f".{cache_path.name}.",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        os.chmod(temporary_path, 0o600)
        temporary_path.replace(cache_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
