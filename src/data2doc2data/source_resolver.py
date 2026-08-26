"""Local-first source inspection for data, text, and mixed documents."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
from pathlib import Path
import re
from typing import Iterable
import xml.etree.ElementTree as ElementTree
import zipfile

from .analysis import MAX_CSV_BYTES
from .documents import DocumentSection, ParsedDocument, parse_document


MAX_SOURCE_COUNT = 200
CONVERTIBLE_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx", ".xls", ".pptx", ".html", ".htm"})
SUPPORTED_SUFFIXES = CONVERTIBLE_SUFFIXES | {".csv", ".md", ".txt"}


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
        expanded: list[Path] = []
        for requested_path in requested:
            path = self.approved_path(requested_path)
            if path.is_dir():
                for candidate in sorted(path.rglob("*")):
                    if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES:
                        expanded.append(self.approved_path(candidate))
                    if len(expanded) > MAX_SOURCE_COUNT:
                        raise SourceResolverError(f"source limit is {MAX_SOURCE_COUNT}")
                continue
            expanded.append(path)
            if len(expanded) > MAX_SOURCE_COUNT:
                raise SourceResolverError(f"source limit is {MAX_SOURCE_COUNT}")
        datasets: list[ResolvedDataset] = []
        documents: list[ParsedDocument] = []
        diagnostics: list[SourceDiagnostic] = []
        for path in dict.fromkeys(expanded):
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
                if suffix in {".html", ".htm"}:
                    document, embedded = _read_html(path)
                    documents.append(document)
                    datasets.extend(embedded)
                    continue
                if suffix == ".docx":
                    document, embedded = _read_docx(path)
                    documents.append(document)
                    datasets.extend(embedded)
                    continue
                if suffix == ".xlsx":
                    datasets.extend(_read_xlsx(path))
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
            except (OSError, UnicodeError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
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


class _HtmlReportParser(HTMLParser):
    """Extract visible narrative, accessible chart labels, and structured tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.narrative: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in {"img", "svg", "canvas"}:
            label = attributes.get("alt") or attributes.get("aria-label") or attributes.get("title")
            if label and label.strip():
                self.narrative.append(label.strip())
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._ignored_depth or not data.strip():
            return
        value = data.strip()
        if self._cell is not None:
            self._cell.append(value)
        elif self._table is None:
            self.narrative.append(value)


def _read_html(path: Path) -> tuple[ParsedDocument, tuple[ResolvedDataset, ...]]:
    content = path.read_bytes()
    if not content or len(content) > MAX_CSV_BYTES:
        raise SourceResolverError("HTML source is empty or oversized")
    parser = _HtmlReportParser()
    parser.feed(content.decode("utf-8-sig"))
    parser.close()
    text = "\n".join(parser.narrative).strip()
    if not text:
        text = path.stem
    digest = hashlib.sha256(content).hexdigest()
    section = DocumentSection(path.stem, text, 1, max(1, len(text.splitlines())))
    document = ParsedDocument(path.name, path.stem, "html", digest, (section,))
    datasets: list[ResolvedDataset] = []
    for table in parser.tables:
        if len(table) < 2:
            continue
        fields = tuple(cell.strip() for cell in table[0])
        if not fields or any(not field for field in fields) or len(set(fields)) != len(fields):
            continue
        rows = tuple(dict(zip(fields, cells, strict=True)) for cells in table[1:] if len(cells) == len(fields))
        if not rows:
            continue
        serialized = json.dumps({"fields": fields, "rows": rows}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        datasets.append(
            ResolvedDataset(
                f"{path.name}#table-{len(datasets) + 1}",
                hashlib.sha256(serialized).hexdigest(),
                fields,
                rows,
                "embedded_html_table",
            )
        )
    return document, tuple(datasets)


_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SHEET_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _read_docx(path: Path) -> tuple[ParsedDocument, tuple[ResolvedDataset, ...]]:
    with _bounded_office_archive(path) as archive:
        root = _safe_xml(archive.read("word/document.xml"))
    body = root.find(f"{_WORD_NAMESPACE}body")
    if body is None:
        raise SourceResolverError("Word document does not contain a body")
    narrative = []
    for paragraph in body.findall(f"{_WORD_NAMESPACE}p"):
        value = "".join(part.text or "" for part in paragraph.iter(f"{_WORD_NAMESPACE}t")).strip()
        if value:
            narrative.append(value)
    for element in root.iter():
        if element.tag.endswith("}docPr"):
            label = element.attrib.get("descr") or element.attrib.get("title")
            if label and label.strip():
                narrative.append(label.strip())
    datasets = []
    for table in body.iter(f"{_WORD_NAMESPACE}tbl"):
        rows = []
        for row in table.findall(f"{_WORD_NAMESPACE}tr"):
            rows.append(
                [
                    "".join(part.text or "" for part in cell.iter(f"{_WORD_NAMESPACE}t")).strip()
                    for cell in row.findall(f"{_WORD_NAMESPACE}tc")
                ]
            )
        dataset = _embedded_table(path.name, rows, len(datasets) + 1, "embedded_docx_table")
        if dataset is not None:
            datasets.append(dataset)
    text = "\n".join(narrative).strip() or path.stem
    section = DocumentSection(path.stem, text, 1, max(1, len(text.splitlines())))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ParsedDocument(path.name, path.stem, "docx", digest, (section,)), tuple(datasets)


def _read_xlsx(path: Path) -> tuple[ResolvedDataset, ...]:
    with _bounded_office_archive(path) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = _safe_xml(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(part.text or "" for part in item.iter(f"{_SHEET_NAMESPACE}t"))
                for item in strings.findall(f"{_SHEET_NAMESPACE}si")
            ]
        datasets = []
        worksheets = sorted(
            name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", name)
        )
        for sheet_name in worksheets[:50]:
            root = _safe_xml(archive.read(sheet_name))
            rows = []
            for row in root.iter(f"{_SHEET_NAMESPACE}row"):
                cells: dict[int, str] = {}
                for index, cell in enumerate(row.findall(f"{_SHEET_NAMESPACE}c")):
                    match = re.match(r"([A-Z]+)", cell.attrib.get("r", ""))
                    position = _excel_column(match.group(1)) if match else index
                    value = cell.find(f"{_SHEET_NAMESPACE}v")
                    if cell.attrib.get("t") == "inlineStr":
                        parsed = "".join(part.text or "" for part in cell.iter(f"{_SHEET_NAMESPACE}t"))
                    elif cell.attrib.get("t") == "s":
                        reference = int(value.text or "-1") if value is not None else -1
                        if not 0 <= reference < len(shared):
                            raise SourceResolverError("spreadsheet contains an invalid shared-string reference")
                        parsed = shared[reference]
                    else:
                        parsed = value.text or "" if value is not None else ""
                    cells[position] = parsed.strip()
                if cells:
                    rows.append([cells.get(index, "") for index in range(max(cells) + 1)])
            dataset = _embedded_table(path.name, rows, len(datasets) + 1, "xlsx_worksheet")
            if dataset is not None:
                datasets.append(_normalize_excel_dates(dataset))
    if not datasets:
        raise SourceResolverError("spreadsheet contains no usable tabular worksheet")
    return tuple(datasets)


def _bounded_office_archive(path: Path) -> zipfile.ZipFile:
    if path.stat().st_size > MAX_CSV_BYTES:
        raise SourceResolverError("Office source is oversized")
    archive = zipfile.ZipFile(path)
    members = archive.infolist()
    if len(members) > 500 or sum(member.file_size for member in members) > MAX_CSV_BYTES * 3:
        archive.close()
        raise SourceResolverError("Office archive exceeds safe extraction limits")
    if any(member.filename.startswith("/") or ".." in Path(member.filename).parts for member in members):
        archive.close()
        raise SourceResolverError("Office archive contains an unsafe member path")
    return archive


def _safe_xml(content: bytes) -> ElementTree.Element:
    if len(content) > MAX_CSV_BYTES:
        raise SourceResolverError("Office XML part exceeds safe limits")
    lowered = content.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise SourceResolverError("Office XML entities are not supported")
    return ElementTree.fromstring(content)


def _excel_column(value: str) -> int:
    index = 0
    for character in value:
        index = index * 26 + ord(character) - ord("A") + 1
    if index > 16_384:
        raise SourceResolverError("spreadsheet column exceeds safe limits")
    return index - 1


def _embedded_table(name: str, rows: list[list[str]], index: int, origin: str) -> ResolvedDataset | None:
    if len(rows) < 2:
        return None
    fields = tuple(cell.strip() for cell in rows[0])
    if not fields or any(not field for field in fields) or len(set(fields)) != len(fields):
        return None
    records = tuple(dict(zip(fields, row, strict=True)) for row in rows[1:] if len(row) == len(fields) and any(row))
    if not records:
        return None
    serialized = json.dumps({"fields": fields, "rows": records}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return ResolvedDataset(
        f"{name}#table-{index}",
        hashlib.sha256(serialized).hexdigest(),
        fields,
        records,
        origin,
    )


def _normalize_excel_dates(dataset: ResolvedDataset) -> ResolvedDataset:
    if "date" not in dataset.fields:
        return dataset
    rows = []
    for record in dataset.rows:
        current = dict(record)
        value = current.get("date", "")
        if re.fullmatch(r"[0-9]+(?:\.0+)?", value):
            serial = int(float(value))
            if 1 <= serial <= 2_958_465:
                current["date"] = (datetime(1899, 12, 30) + timedelta(days=serial)).date().isoformat()
        rows.append(current)
    return ResolvedDataset(dataset.name, dataset.sha256, dataset.fields, tuple(rows), dataset.origin)


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
