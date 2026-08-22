"""Bounded Markdown/TXT corpus parsing with exact local provenance."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re


MAX_DOCUMENT_BYTES = 1_000_000
MAX_DOCUMENTS = 200


class DocumentError(ValueError):
    pass


@dataclass(frozen=True)
class DocumentSection:
    heading: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class ParsedDocument:
    name: str
    title: str
    format: str
    sha256: str
    sections: tuple[DocumentSection, ...]


@dataclass(frozen=True)
class DocumentFailure:
    name: str
    error: str


@dataclass(frozen=True)
class DocumentCorpus:
    corpus_id: str
    documents: tuple[ParsedDocument, ...]
    failures: tuple[DocumentFailure, ...]
    duplicate_count: int


def parse_document(path: Path) -> ParsedDocument:
    if path.suffix.lower() not in {".md", ".txt"}:
        raise DocumentError("document format must be Markdown or TXT")
    try:
        content = path.read_bytes()
        if len(content) > MAX_DOCUMENT_BYTES:
            raise DocumentError("document is too large")
        text = content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocumentError(f"cannot read document: {path.name}") from exc
    if not text.strip():
        raise DocumentError("document is empty")
    lines = text.splitlines()
    sections: list[DocumentSection] = []
    heading = path.stem
    start = 1
    buffered: list[str] = []
    title = path.stem
    for line_number, line in enumerate(lines, start=1):
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line) if path.suffix.lower() == ".md" else None
        if match:
            if buffered:
                sections.append(DocumentSection(heading, "\n".join(buffered).strip(), start, line_number - 1))
            heading = match.group(1).strip()
            if not sections and title == path.stem:
                title = heading
            start = line_number
            buffered = [line]
        else:
            buffered.append(line)
    if buffered:
        sections.append(DocumentSection(heading, "\n".join(buffered).strip(), start, len(lines)))
    sections = [section for section in sections if section.text]
    return ParsedDocument(
        name=path.name,
        title=title,
        format=path.suffix.lower().lstrip("."),
        sha256=hashlib.sha256(content).hexdigest(),
        sections=tuple(sections),
    )


def build_document_corpus(paths: tuple[Path, ...], corpus_id: str) -> DocumentCorpus:
    documents: list[ParsedDocument] = []
    failures: list[DocumentFailure] = []
    digests: set[str] = set()
    duplicate_count = 0
    for path in sorted(paths, key=lambda item: str(item))[:MAX_DOCUMENTS]:
        try:
            document = parse_document(path)
        except DocumentError as exc:
            failures.append(DocumentFailure(path.name, str(exc)))
            continue
        if document.sha256 in digests:
            duplicate_count += 1
            continue
        digests.add(document.sha256)
        documents.append(document)
    if len(paths) > MAX_DOCUMENTS:
        failures.append(DocumentFailure("remaining documents", f"document limit is {MAX_DOCUMENTS}"))
    return DocumentCorpus(corpus_id, tuple(documents), tuple(failures), duplicate_count)
