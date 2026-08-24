"""Safe, versioned declarative dashboard contracts."""

from __future__ import annotations

from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import Any, Mapping

from .analysis_cycle import AnalysisCycle
from .artifacts import ArtifactStore


CONTRACT_VERSION = 1
MAX_RESULT_ROWS = 1000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_FIELD = re.compile(r"^[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_.\-\u4e00-\u9fff]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UNSAFE_EXPRESSION = re.compile(r"(?i)(\bselect\b|\bimport\b|<script|javascript:|;|\beval\s*\()")
_MARKS = frozenset({"line", "bar", "point", "area"})
_CHANNELS = frozenset({"x", "y", "color", "size", "shape", "tooltip"})
_TYPES = frozenset({"temporal", "quantitative", "nominal", "ordinal"})
_TRANSFORMS = frozenset({"aggregate", "filter", "bin", "sort", "top_n"})
_TRANSFORM_KEYS = {
    "aggregate": frozenset({"type", "op", "field", "groupby"}),
    "filter": frozenset({"type", "field", "op", "value"}),
    "bin": frozenset({"type", "field", "maxbins"}),
    "sort": frozenset({"type", "field", "order"}),
    "top_n": frozenset({"type", "field", "n"}),
}


class DashboardContractError(ValueError):
    pass


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DashboardContractError(f"{field} must be a stable identifier")
    return value


def _text(value: object, field: str, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise DashboardContractError(f"{field} must be bounded non-empty text")
    return value.strip()


@dataclass(frozen=True)
class QueryProvenance:
    snapshot_id: str
    sha256: str
    expression: str
    fields: tuple[str, ...]
    result_row_count: int

    def __post_init__(self) -> None:
        _identifier(self.snapshot_id, "snapshot_id")
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            raise DashboardContractError("sha256 must be a lowercase SHA-256 digest")
        expression = _text(self.expression, "expression", 1000)
        if _UNSAFE_EXPRESSION.search(expression):
            raise DashboardContractError("expression must be descriptive, not executable")
        if not self.fields or any(not isinstance(field, str) or not _FIELD.fullmatch(field) for field in self.fields):
            raise DashboardContractError("fields must contain safe field names")
        if not isinstance(self.result_row_count, int) or not 0 <= self.result_row_count <= MAX_RESULT_ROWS:
            raise DashboardContractError(f"result row count must be between 0 and {MAX_RESULT_ROWS}")

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "sha256": self.sha256,
            "expression": self.expression,
            "fields": list(self.fields),
            "result_row_count": self.result_row_count,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> QueryProvenance:
        fields = payload.get("fields", ())
        if not isinstance(fields, (list, tuple)):
            raise DashboardContractError("fields must be a list")
        return cls(
            str(payload.get("snapshot_id", "")),
            str(payload.get("sha256", "")),
            str(payload.get("expression", "")),
            tuple(str(field) for field in fields),
            payload.get("result_row_count"),
        )


@dataclass(frozen=True)
class FlintChartSpec:
    mark: str
    encoding: Mapping[str, Mapping[str, str]]
    transforms: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.mark not in _MARKS:
            raise DashboardContractError(f"unsupported chart mark: {self.mark!r}")
        if not isinstance(self.encoding, Mapping):
            raise DashboardContractError("encoding must be an object")
        for channel, definition in self.encoding.items():
            if channel not in _CHANNELS or not isinstance(definition, Mapping):
                raise DashboardContractError("encoding channel is unsupported")
            field = definition.get("field")
            if not isinstance(field, str) or not _FIELD.fullmatch(field) or field == "__proto__":
                raise DashboardContractError("encoding field is unsafe")
            if definition.get("type") not in _TYPES:
                raise DashboardContractError("encoding type is unsupported")
        for transform in self.transforms:
            if not isinstance(transform, Mapping) or transform.get("type") not in _TRANSFORMS:
                raise DashboardContractError("chart transform is unsupported")
            transform_type = transform["type"]
            if not set(transform).issubset(_TRANSFORM_KEYS[transform_type]):
                raise DashboardContractError("chart transform contains unsupported fields")
            field = transform.get("field")
            if field is not None and (not isinstance(field, str) or not _FIELD.fullmatch(field)):
                raise DashboardContractError("chart transform field is unsafe")
            groupby = transform.get("groupby", ())
            if not isinstance(groupby, (list, tuple)) or any(
                not isinstance(item, str) or not _FIELD.fullmatch(item) for item in groupby
            ):
                raise DashboardContractError("chart transform groupby is unsafe")
            if transform_type == "aggregate" and transform.get("op") not in {"count", "sum", "mean", "min", "max"}:
                raise DashboardContractError("chart transform aggregation is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "mark": self.mark,
            "encoding": {channel: dict(definition) for channel, definition in self.encoding.items()},
            "transforms": [dict(transform) for transform in self.transforms],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> FlintChartSpec:
        encoding = payload.get("encoding", {})
        transforms = payload.get("transforms", ())
        if not isinstance(encoding, Mapping) or not isinstance(transforms, (list, tuple)):
            raise DashboardContractError("invalid chart specification")
        return cls(str(payload.get("mark", "")), dict(encoding), tuple(dict(item) for item in transforms))


@dataclass(frozen=True)
class DashboardBlock:
    block_id: str
    kind: str
    title: str
    provenance: QueryProvenance
    value: Any = None
    chart: FlintChartSpec | None = None
    data: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.block_id, "block_id")
        _text(self.title, "title", 200)
        if self.kind not in {"kpi", "chart", "table"}:
            raise DashboardContractError("block kind is unsupported")
        if self.kind == "chart" and self.chart is None:
            raise DashboardContractError("chart block requires a chart specification")
        if self.kind != "chart" and self.chart is not None:
            raise DashboardContractError("only chart blocks may contain a chart specification")
        if self.kind == "kpi" and self.value is None:
            raise DashboardContractError("kpi block requires a value")
        if self.data and len(self.data) != self.provenance.result_row_count and self.kind in {"chart", "table"}:
            raise DashboardContractError("block data must match provenance result row count")

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "block_id": self.block_id,
            "kind": self.kind,
            "title": self.title,
            "provenance": self.provenance.to_dict(),
            "value": self.value,
            "data": [dict(row) for row in self.data],
        }
        if self.chart is not None:
            payload["chart"] = self.chart.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DashboardBlock:
        provenance = payload.get("provenance")
        chart = payload.get("chart")
        data = payload.get("data", ())
        if not isinstance(provenance, Mapping) or not isinstance(data, (list, tuple)):
            raise DashboardContractError("invalid dashboard block")
        return cls(
            block_id=str(payload.get("block_id", "")),
            kind=str(payload.get("kind", "")),
            title=str(payload.get("title", "")),
            provenance=QueryProvenance.from_dict(provenance),
            value=payload.get("value"),
            chart=FlintChartSpec.from_dict(chart) if isinstance(chart, Mapping) else None,
            data=tuple(dict(row) for row in data),
        )


@dataclass(frozen=True)
class DashboardSpec:
    dashboard_id: str
    title: str
    blocks: tuple[DashboardBlock, ...]
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != CONTRACT_VERSION:
            raise DashboardContractError("unsupported dashboard contract version")
        _identifier(self.dashboard_id, "dashboard_id")
        _text(self.title, "title", 200)
        if not self.blocks:
            raise DashboardContractError("dashboard must contain at least one block")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise DashboardContractError("dashboard block IDs must be unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "dashboard_id": self.dashboard_id,
            "title": self.title,
            "blocks": [block.to_dict() for block in self.blocks],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> DashboardSpec:
        blocks = payload.get("blocks", ())
        if not isinstance(blocks, (list, tuple)):
            raise DashboardContractError("blocks must be a list")
        return cls(
            dashboard_id=str(payload.get("dashboard_id", "")),
            title=str(payload.get("title", "")),
            blocks=tuple(DashboardBlock.from_dict(block) for block in blocks),
            contract_version=payload.get("contract_version"),
        )


@dataclass(frozen=True)
class ArtifactProvenance:
    artifact_ref: str
    method: str
    sample_size: int
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.artifact_ref, "artifact_ref")
        _text(self.method, "method", 120)
        if not isinstance(self.sample_size, int) or self.sample_size < 0:
            raise DashboardContractError("artifact sample size must be non-negative")
        object.__setattr__(self, "limitations", tuple(self.limitations))

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_ref": self.artifact_ref,
            "method": self.method,
            "sample_size": self.sample_size,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class ArtifactDashboardBlock:
    block_id: str
    kind: str
    title: str
    status: str
    provenance: ArtifactProvenance
    observations: Mapping[str, object]

    def __post_init__(self) -> None:
        _identifier(self.block_id, "block_id")
        _text(self.title, "title", 200)
        object.__setattr__(self, "observations", MappingProxyType(dict(self.observations)))

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "provenance": self.provenance.to_dict(),
            "observations": dict(self.observations),
        }


@dataclass(frozen=True)
class ArtifactDashboardSpec:
    dashboard_id: str
    blocks: tuple[ArtifactDashboardBlock, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": 1,
            "dashboard_id": self.dashboard_id,
            "blocks": [block.to_dict() for block in self.blocks],
        }


def build_artifact_dashboard(cycle: AnalysisCycle, store: ArtifactStore) -> ArtifactDashboardSpec:
    blocks = []
    kind_by_method = {
        "detect_anomalies": "anomalies",
        "detect_change_points": "change_point",
        "decompose_change": "contribution",
        "segment_rank": "segments",
        "correlate_metrics": "relationship",
        "compare_groups": "groups",
        "compare_periods": "period_comparison",
        "topic_metric_alignment": "cross_modal",
        "text_metric_lag": "cross_modal_lag",
        "explanatory_segments": "cross_modal_segments",
    }
    for artifact_ref in cycle.artifact_refs:
        record = store.load(artifact_ref)
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record.get("kind") == "analytical":
            method = str(payload.get("method", "unknown"))
            blocks.append(
                ArtifactDashboardBlock(
                    f"block-{artifact_ref}",
                    kind_by_method.get(method, "diagnostic"),
                    str(payload.get("summary", method))[:200],
                    str(payload.get("status", "completed")),
                    ArtifactProvenance(
                        artifact_ref,
                        method,
                        int(payload.get("sample_size", 0)),
                        tuple(str(item) for item in payload.get("limitations", [])),
                    ),
                    dict(payload.get("observations", {})),
                )
            )
        elif record.get("kind") == "text_ml":
            method = str(payload.get("method", "text_ml"))
            blocks.append(
                ArtifactDashboardBlock(
                    f"block-{artifact_ref}",
                    "text_ml",
                    "文本主题与聚类",
                    str(payload.get("status", "completed")),
                    ArtifactProvenance(artifact_ref, method, int(payload.get("document_count", 0))),
                    {
                        "topics": payload.get("topics", []),
                        "clusters": payload.get("clusters", []),
                        "word_cloud_svg": payload.get("word_cloud_svg", ""),
                    },
                )
            )
    return ArtifactDashboardSpec(f"dashboard-{cycle.cycle_id}", tuple(blocks))
