"""Local-first source inspection for data, text, and mixed documents."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import re
from typing import Iterable

from .analysis import MAX_CSV_BYTES
from .documents import DocumentSection, ParsedDocument, parse_document


MAX_SOURCE_COUNT = 200
CONVERTIBLE_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".html", ".htm"})


class SourceResolverError(ValueError):
    """Raised when source inspection cannot proceed safely."""


@dataclass(frozen=True)
class ResolvedDataset:
    name: str
    sha256: str
    fields: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    origin: str

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class SourceDiagnostic:
    name: str
    message: str


@dataclass(frozen=True)
class ResolvedSources:
    datasets: tuple[ResolvedDataset, ...]
    documents: tuple[ParsedDocument, ...]
    diagnostics: tuple[SourceDiagnostic, ...]

    @property
    def modalities(self) -> tuple[str, ...]:
        values = []
        if self.datasets:
            values.append("data")
        if self.documents:
            values.append("text")
        return tuple(values)


class SourceResolver:
    def __init__(self, allowed_roots: Iterable[Path] = ()) -> None:
        self.allowed_roots = tuple(path.expanduser().resolve() for path in allowed_roots)

    def resolve(self, paths: Iterable[Path]) -> ResolvedSources:
        requested = tuple(paths)
        if not requested:
            raise SourceResolverError("at least one source is required")
        if len(requested) > MAX_SOURCE_COUNT:
            raise SourceResolverError(f"source limit is {MAX_SOURCE_COUNT}")
        datasets: list[ResolvedDataset] = []
        documents: list[ParsedDocument] = []
        diagnostics: list[SourceDiagnostic] = []
        for requested_path in requested:
            path = self.approved_path(requested_path)
            if not path.is_file():
                diagnostics.append(SourceDiagnostic(path.name, "source is not a file"))
                continue
            suffix = path.suffix.lower()
            try:
                if suffix == ".csv":
                    datasets.append(_read_csv(path))
                    continue
                if suffix in {".md", ".txt"}:
                    document = parse_document(path)
                    documents.append(document)
                    if suffix == ".md":
                        datasets.extend(_markdown_tables(path))
                    continue
                if suffix in CONVERTIBLE_SUFFIXES:
                    converted = _convert_optional(path)
                    if converted is None:
                        diagnostics.append(
                            SourceDiagnostic(
                                path.name,
                                "optional MarkItDown converter is unavailable for this format",
                            )
                        )
                        continue
                    documents.append(converted)
                    continue
                diagnostics.append(SourceDiagnostic(path.name, f"unsupported source format: {suffix or 'none'}"))
            except (OSError, UnicodeError, ValueError) as exc:
                diagnostics.append(SourceDiagnostic(path.name, str(exc)[:300]))
        return ResolvedSources(tuple(datasets), tuple(documents), tuple(diagnostics))

    def approved_path(self, requested: Path) -> Path:
        """Resolve a path and enforce the configured local containment boundary."""
        path = requested.expanduser().resolve()
        if self.allowed_roots and not any(path == root or root in path.parents for root in self.allowed_roots):
            raise SourceResolverError("source must remain inside approved roots")
        return path


def _read_csv(path: Path) -> ResolvedDataset:
    content = path.read_bytes()
    if not content or len(content) > MAX_CSV_BYTES:
        raise SourceResolverError("CSV source is empty or oversized")
    text = content.decode("utf-8")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise SourceResolverError("CSV header is missing")
    fields = tuple(field.strip() for field in reader.fieldnames if field and field.strip())
    if not fields:
        raise SourceResolverError("CSV has no usable fields")
    rows = tuple({field: str(row.get(field, "")).strip() for field in fields} for row in reader)
    if not rows:
        raise SourceResolverError("CSV has no data rows")
    return ResolvedDataset(path.name, hashlib.sha256(content).hexdigest(), fields, rows, "file")


def _markdown_tables(path: Path) -> tuple[ResolvedDataset, ...]:
    content = path.read_bytes()
    if not content or len(content) > MAX_CSV_BYTES:
        raise SourceResolverError("Markdown source is empty or oversized")
    lines = content.decode("utf-8").splitlines()
    datasets: list[ResolvedDataset] = []
    index = 0
    while index + 2 < len(lines):
        header = _table_cells(lines[index])
        separator = _table_cells(lines[index + 1])
        if not header or len(separator) != len(header) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            index += 1
            continue
        rows = []
        cursor = index + 2
        while cursor < len(lines):
            cells = _table_cells(lines[cursor])
            if len(cells) != len(header):
                break
            rows.append(dict(zip(header, cells, strict=True)))
            cursor += 1
        if rows:
            serialized = "\n".join(lines[index:cursor]).encode("utf-8")
            datasets.append(
                ResolvedDataset(
                    f"{path.name}#table-{len(datasets) + 1}",
                    hashlib.sha256(serialized).hexdigest(),
                    tuple(header),
                    tuple(rows),
                    "embedded_markdown_table",
                )
            )
        index = max(cursor, index + 1)
    return tuple(datasets)


def _table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _convert_optional(path: Path) -> ParsedDocument | None:
    if importlib.util.find_spec("markitdown") is None:
        return None
    from markitdown import MarkItDown  # type: ignore[import-not-found]

    result = MarkItDown(enable_plugins=False).convert(str(path))
    text = str(getattr(result, "text_content", "")).strip()
    if not text:
        raise SourceResolverError("document converter returned no text")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    section = DocumentSection(path.stem, text, 1, max(1, len(text.splitlines())))
    return ParsedDocument(path.name, path.stem, path.suffix.lower().lstrip("."), digest, (section,))
