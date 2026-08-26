"""Validated local analytical tables with optional business dimensions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .analysis import MAX_CSV_BYTES


REQUIRED_FIELDS = ("date", "metric", "value")
_FIELD_NAME = re.compile(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{0,127}$")


class AnalyticalTableError(ValueError):
    """Raised when a local table cannot produce trustworthy analytical rows."""


@dataclass(frozen=True)
class AnalyticalRow:
    date: date
    metric: str
    value: float
    dimensions: Mapping[str, str]
    source_row: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))


@dataclass(frozen=True)
class AnalyticalTable:
    snapshot_id: str
    sha256: str
    fields: tuple[str, ...]
    dimensions: tuple[str, ...]
    rows: tuple[AnalyticalRow, ...]
    source_row_count: int
    missing_required_count: int


def load_analytical_table(path: Path, snapshot_id: str) -> AnalyticalTable:
    try:
        content = path.read_bytes()
        if not content or len(content) > MAX_CSV_BYTES:
            raise AnalyticalTableError("CSV source is empty or oversized")
        reader = csv.DictReader(content.decode("utf-8").splitlines())
        fields = _validated_fields(reader.fieldnames)
        raw_rows = list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise AnalyticalTableError(f"cannot load analytical CSV: {exc}") from exc
    if not raw_rows:
        raise AnalyticalTableError("CSV has no data rows")

    dimensions = tuple(field for field in fields if field not in REQUIRED_FIELDS)
    rows: list[AnalyticalRow] = []
    missing_required_count = 0
    for source_row, raw in enumerate(raw_rows, start=2):
        raw_date = str(raw.get("date") or "").strip()
        metric = str(raw.get("metric") or "").strip().lower()
        raw_value = str(raw.get("value") or "").strip()
        missing = sum(not value for value in (raw_date, metric, raw_value))
        if missing:
            missing_required_count += missing
            continue
        try:
            parsed_date = date.fromisoformat(raw_date)
            value = float(raw_value)
        except ValueError as exc:
            raise AnalyticalTableError(f"CSV contains an invalid date or value: {exc}") from exc
        if not math.isfinite(value):
            raise AnalyticalTableError("CSV values must be finite")
        rows.append(
            AnalyticalRow(
                parsed_date,
                metric,
                value,
                {field: str(raw.get(field) or "").strip() for field in dimensions},
                source_row,
            )
        )
    if not rows:
        raise AnalyticalTableError("CSV has no valid analytical rows")
    return AnalyticalTable(
        snapshot_id,
        hashlib.sha256(content).hexdigest(),
        fields,
        dimensions,
        tuple(rows),
        len(raw_rows),
        missing_required_count,
    )


def _validated_fields(raw_fields: list[str] | None) -> tuple[str, ...]:
    if not raw_fields:
        raise AnalyticalTableError("CSV header is missing")
    fields = tuple(str(field or "").strip() for field in raw_fields)
    if any(not field or not _FIELD_NAME.fullmatch(field) for field in fields):
        raise AnalyticalTableError("CSV contains an invalid field name")
    if len(fields) != len(set(fields)):
        raise AnalyticalTableError("CSV field names must be unique")
    missing = set(REQUIRED_FIELDS) - set(fields)
    if missing:
        raise AnalyticalTableError(f"CSV must include {', '.join(REQUIRED_FIELDS)} columns")
    return fields
