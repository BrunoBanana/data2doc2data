"""Ingestion layer: turn arbitrary local files or API snapshots into standard metric rows.

The deterministic engine only understands ``date,metric,value`` rows. This
module is the bridge: it probes local files (CSV / JSON / XLSX) or API
snapshots, proposes a field mapping, and — after the user confirms the plan —
converts the source into standard metric rows with row-level provenance.
Agent-assisted proposals reuse the same plan schema, so a plan proposed by an
agent and confirmed by a human is indistinguishable from a built-in
suggestion; execution is always deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import csv
import io
import json
from pathlib import Path
import re
import time
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile

from .metrics import MetricRow


MAX_SOURCE_BYTES = 5_000_000
MAX_SAMPLE_ROWS = 5
MAX_API_REDIRECTS = 3
SUPPORTED_FORMATS = ("csv", "json", "xlsx")

_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_UNSAFE_REQUEST_HEADERS = frozenset(
    {"connection", "content-length", "host", "proxy-authorization", "transfer-encoding"}
)
_CROSS_ORIGIN_SECRET_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization", "x-api-key"}
)

_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y.%m.%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y%m%d",
    "%Y年%m月%d日",
)
_EXCEL_EPOCH = date(1899, 12, 30)


class IngestionError(ValueError):
    """Raised when a source cannot be probed or a plan cannot be applied."""


@dataclass(frozen=True)
class IngestionPlan:
    """A confirmed field mapping from an arbitrary source to metric rows."""

    format: Literal["csv", "json", "xlsx"]
    date_field: str
    metric_field: str
    value_field: str
    records_path: str = ""
    sheet: str = ""
    date_format: str = ""

    def __post_init__(self) -> None:
        if self.format not in SUPPORTED_FORMATS:
            raise IngestionError(f"unsupported ingestion format: {self.format}")
        for name in ("date_field", "metric_field", "value_field"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise IngestionError(f"ingestion plan field '{name}' is required")

    def to_dict(self) -> dict[str, str]:
        return {
            "format": self.format,
            "date_field": self.date_field,
            "metric_field": self.metric_field,
            "value_field": self.value_field,
            "records_path": self.records_path,
            "sheet": self.sheet,
            "date_format": self.date_format,
        }

    @classmethod
    def from_dict(cls, value: object) -> "IngestionPlan":
        if not isinstance(value, dict):
            raise IngestionError("ingestion plan must be a JSON object")
        try:
            return cls(
                format=value["format"],
                date_field=value["date_field"],
                metric_field=value["metric_field"],
                value_field=value["value_field"],
                records_path=str(value.get("records_path", "")),
                sheet=str(value.get("sheet", "")),
                date_format=str(value.get("date_format", "")),
            )
        except KeyError as error:
            raise IngestionError(f"ingestion plan is missing '{error.args[0]}'") from error


@dataclass(frozen=True)
class SourcePreview:
    """Structure summary of a source file, for the UI and for agent proposals."""

    format: str
    fields: tuple[str, ...]
    sample_rows: tuple[dict[str, str], ...]
    row_count: int | None
    sheets: tuple[str, ...] = ()
    header_values: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "fields": list(self.fields),
            "sample_rows": [dict(row) for row in self.sample_rows],
            "row_count": self.row_count,
            "sheets": list(self.sheets),
            "header_values": list(self.header_values),
        }


@dataclass(frozen=True)
class IngestionResult:
    rows: tuple[MetricRow, ...]
    warnings: tuple[str, ...]
    skipped: int

    def to_dict(self) -> dict[str, object]:
        return {
            "row_count": len(self.rows),
            "skipped": self.skipped,
            "warnings": list(self.warnings[:20]),
            "metrics": sorted({row.metric for row in self.rows}),
            "date_range": [
                str(min((row.date for row in self.rows), default="")),
                str(max((row.date for row in self.rows), default="")),
            ],
        }


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"csv", "tsv"}:
        return "csv"
    if suffix == "json":
        return "json"
    if suffix in {"xlsx", "xlsm"}:
        return "xlsx"
    raise IngestionError(
        f"无法识别文件格式：{path.name}（支持 {', '.join(SUPPORTED_FORMATS)}）"
    )


def preview_source(path: Path) -> SourcePreview:
    """Probe a local file and summarize its structure without transforming it."""
    resolved = path.expanduser()
    if not resolved.is_file():
        raise IngestionError(f"文件不存在：{resolved}")
    size = resolved.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise IngestionError(f"文件过大（{size} 字节，上限 {MAX_SOURCE_BYTES}）")
    fmt = detect_format(resolved)
    if fmt == "csv":
        return _preview_csv(resolved)
    if fmt == "json":
        return _preview_json(resolved)
    return _preview_xlsx(resolved)


def suggest_plan(preview: SourcePreview) -> IngestionPlan | None:
    """Best-effort built-in mapping suggestion; agents may propose the same schema."""
    lookup = {
        name.strip().lower(): name
        for name in preview.fields
    }
    date_field = _match_field(lookup, ("date", "日期", "时间", "day", "ds"))
    metric_field = _match_field(lookup, ("metric", "指标", "度量", "indicator", "name"))
    value_field = _match_field(lookup, ("value", "数值", "值", "val", "amount"))
    if date_field and metric_field and value_field:
        return IngestionPlan(
            format=preview.format,
            date_field=date_field,
            metric_field=metric_field,
            value_field=value_field,
            records_path=_records_path_hint(preview),
            sheet=preview.sheets[0] if preview.sheets else "",
        )
    return None


def apply_plan(path: Path, plan: IngestionPlan) -> IngestionResult:
    """Execute a confirmed plan deterministically and validate every row."""
    resolved = path.expanduser()
    if not resolved.is_file():
        raise IngestionError(f"文件不存在：{resolved}")
    records = _read_records(resolved, plan)
    if not records:
        raise IngestionError("按映射方案没有读到任何记录，请检查字段选择")
    rows: list[MetricRow] = []
    warnings: list[str] = []
    skipped = 0
    for index, record in enumerate(records, start=2):
        raw_date = str(record.get(plan.date_field, "")).strip()
        raw_metric = str(record.get(plan.metric_field, "")).strip()
        raw_value = str(record.get(plan.value_field, "")).strip()
        parsed_date = _parse_date(raw_date, plan.date_format)
        try:
            parsed_value = float(raw_value.replace(",", "")) if raw_value else None
        except ValueError:
            parsed_value = None
        if parsed_date is None or not raw_metric or parsed_value is None or parsed_value != parsed_value:
            skipped += 1
            if len(warnings) < 20:
                warnings.append(f"第 {index} 行被跳过：日期/指标/数值无法解析（{raw_date} | {raw_metric} | {raw_value}）")
            continue
        rows.append(MetricRow(date=parsed_date, metric=raw_metric, value=parsed_value, source_row=index))
    if not rows:
        detail = "；".join(warnings[:3]) or "无详细原因"
        raise IngestionError(f"所有记录都无法转换为指标行。{detail}")
    return IngestionResult(rows=tuple(rows), warnings=tuple(warnings), skipped=skipped)


def write_standard_csv(rows: tuple[MetricRow, ...], target: Path) -> Path:
    """Persist converted rows as the standard CSV the engine consumes."""
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "metric", "value"])
    for row in rows:
        writer.writerow([row.date.isoformat(), row.metric, repr(row.value)])
    temporary = target.with_suffix(".tmp")
    temporary.write_text(buffer.getvalue(), encoding="utf-8")
    temporary.replace(target)
    return target


@dataclass(frozen=True)
class ApiSnapshot:
    path: Path
    fetched_at: str
    content_type: str


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        return None


def _build_api_url(url: str, params: dict[str, str] | None = None) -> str:
    if not isinstance(url, str) or not url.strip():
        raise IngestionError("数据 API 地址不能为空")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as error:
        raise IngestionError("数据 API 地址格式无效") from error
    if parsed.scheme.lower() != "https":
        raise IngestionError("数据 API 仅支持 HTTPS 地址")
    if not parsed.hostname or any(character.isspace() for character in parsed.hostname):
        raise IngestionError("数据 API 地址必须包含有效主机名")
    if parsed.username is not None or parsed.password is not None:
        raise IngestionError("数据 API 地址不能包含用户名或密码")
    if port not in {None, 443}:
        raise IngestionError("数据 API 仅允许标准 HTTPS 端口 443")
    if parsed.fragment:
        raise IngestionError("数据 API 地址不能包含片段标识")
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if params:
        if not isinstance(params, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in params.items()
        ):
            raise IngestionError("数据 API 查询参数必须是字符串键值")
        query.extend(params.items())
    path = parsed.path or "/"
    return urlunsplit(("https", parsed.netloc, path, urlencode(query), ""))


def _validated_api_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise IngestionError("数据 API 请求头必须是对象")
    validated: dict[str, str] = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise IngestionError("数据 API 请求头必须是字符串键值")
        normalized = name.strip().lower()
        if not normalized or normalized in _UNSAFE_REQUEST_HEADERS:
            raise IngestionError(f"数据 API 不允许覆盖请求头：{name}")
        if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
            raise IngestionError("数据 API 请求头包含非法换行")
        validated[name] = value
    return validated


def _api_origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or 443


def _open_api_response(opener, url: str, headers: dict[str, str]):
    current_url = url
    current_headers = dict(headers)
    for redirect_count in range(MAX_API_REDIRECTS + 1):
        request = Request(current_url, headers=current_headers)
        try:
            return opener.open(request, timeout=30)
        except HTTPError as error:
            if error.code not in _REDIRECT_CODES:
                raise
            location = error.headers.get("Location") if error.headers else None
            error.close()
            if not location:
                raise IngestionError("数据 API 重定向缺少目标地址") from error
            if redirect_count >= MAX_API_REDIRECTS:
                raise IngestionError("数据 API 重定向次数过多") from error
            next_url = _build_api_url(urljoin(current_url, location))
            if _api_origin(next_url) != _api_origin(current_url):
                current_headers = {
                    name: value
                    for name, value in current_headers.items()
                    if name.lower() not in _CROSS_ORIGIN_SECRET_HEADERS
                }
            current_url = next_url
    raise IngestionError("数据 API 重定向次数过多")


def fetch_api_snapshot(
    url: str,
    target_dir: Path,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> ApiSnapshot:
    """Fetch an HTTPS API into a local, timestamped snapshot; credentials stay in memory."""
    request_url = _build_api_url(url, params)
    request_headers = _validated_api_headers(headers)
    opener = build_opener(ProxyHandler({}), _NoRedirectHandler())
    try:
        with _open_api_response(opener, request_url, request_headers) as response:
            content_type = response.headers.get_content_type()
            body = response.read(MAX_SOURCE_BYTES + 1)
    except HTTPError as error:
        raise IngestionError(f"API 请求失败（HTTP {error.code}）") from error
    except (URLError, OSError) as error:
        raise IngestionError(f"API 请求失败：{error}") from error
    if len(body) > MAX_SOURCE_BYTES:
        raise IngestionError("API 响应过大，超出本地处理上限")
    extension = "json" if "json" in content_type else "csv"
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    snapshot = target_dir / f"api-snapshot-{int(time.time())}.{extension}"
    snapshot.write_bytes(body)
    return ApiSnapshot(path=snapshot, fetched_at=fetched_at, content_type=content_type)


def build_proposal_prompt(preview: SourcePreview, source_path: str) -> str:
    """Prompt for an in-the-loop agent to propose a mapping plan as strict JSON.

    The prompt embeds the probed structure and sample rows so the agent never
    needs file-system access — it only interprets the structure deterministically
    presented by the local service.
    """
    sample = json.dumps([dict(row) for row in preview.sample_rows], ensure_ascii=False)
    return (
        f"请分析以下数据文件的结构（文件：{source_path}，格式 {preview.format}），"
        "并把它的字段映射到 date,metric,value 三列的标准指标数据。\n"
        f"字段/列：{list(preview.fields)}\n"
        f"样例数据：{sample}\n"
        "只返回一个 JSON 对象，不要任何其他文字，格式为：\n"
        '{"format": "csv|json|xlsx", "date_field": "...", "metric_field": "...", '
        '"value_field": "...", "records_path": "json记录数组的路径,非JSON留空", '
        '"sheet": "xlsx工作表名,非XLSX留空", "date_format": "日期格式提示,可留空"}\n'
        "如果这些字段无法映射为指标数据，返回 {\"error\": \"原因\"}。"
    )


def parse_plan_response(text: str) -> IngestionPlan | None:
    """Parse an agent's JSON mapping proposal out of its free-text reply."""
    candidates: list[str] = []
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates.extend(fenced)
    brace = re.search(r"\{[^{}]*\"format\"[^{}]*\}", text, flags=re.DOTALL)
    if brace:
        candidates.append(brace.group(0))
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("error"):
            return None
        if isinstance(payload, dict) and "format" in payload:
            return IngestionPlan.from_dict(payload)
    return None


def _preview_csv(path: Path) -> SourcePreview:
    text = path.read_text(encoding="utf-8-sig", errors="strict")
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as error:
        raise IngestionError("CSV 文件为空") from error
    rows = [row for _, row in zip(range(MAX_SAMPLE_ROWS + 200), reader) if row]
    sample = [dict(zip(header, row)) for row in rows[:MAX_SAMPLE_ROWS]]
    return SourcePreview(
        format="csv",
        fields=tuple(header),
        sample_rows=tuple(sample),
        row_count=len(rows),
    )


def _preview_json(path: Path) -> SourcePreview:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise IngestionError(f"JSON 解析失败：{error}") from error
    records, records_path = _locate_records(payload)
    if not records:
        raise IngestionError("JSON 中没有找到记录数组（对象列表）")
    fields: list[str] = []
    for record in records[:20]:
        if isinstance(record, dict):
            for key in record:
                if key not in fields:
                    fields.append(key)
    sample = tuple(
        {key: _stringify(record.get(key)) for key in fields}
        for record in records[:MAX_SAMPLE_ROWS]
        if isinstance(record, dict)
    )
    preview = SourcePreview(
        format="json",
        fields=tuple(fields),
        sample_rows=sample,
        row_count=len(records),
    )
    object.__setattr__(preview, "_records_path", records_path)
    return preview


def _locate_records(payload: object) -> tuple[list[object], str]:
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload, ""
    if isinstance(payload, dict):
        preferred = ("data", "rows", "records", "results", "items", "list")
        for key in preferred:
            value = payload.get(key)
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return value, key
        for key, value in payload.items():
            if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                return value, key
    raise IngestionError("JSON 顶层不是对象数组，也找不到常见的记录数组字段")


def _records_path_hint(preview: SourcePreview) -> str:
    hint = getattr(preview, "_records_path", "")
    return hint if isinstance(hint, str) else ""


def _preview_xlsx(path: Path) -> SourcePreview:
    sheets, first_sheet_rows = _read_xlsx(path, "")
    if not first_sheet_rows:
        raise IngestionError("XLSX 第一个工作表没有数据")
    width = max(len(row) for row in first_sheet_rows)
    columns = [_column_name(index) for index in range(width)]
    header = first_sheet_rows[0]
    header_like = bool(header) and all(
        cell.strip() and _parse_date(cell) is None and not _is_number(cell)
        for cell in header
        if cell.strip()
    )
    data_rows = first_sheet_rows[1:] if header_like else first_sheet_rows
    sample = tuple(
        {
            _column_name(index): (row[index] if index < len(row) else "")
            for index in range(width)
        }
        for row in data_rows[:MAX_SAMPLE_ROWS]
    )
    return SourcePreview(
        format="xlsx",
        fields=tuple(columns),
        sample_rows=sample,
        row_count=len(data_rows),
        sheets=tuple(sheets),
        header_values=tuple(header) if header_like else (),
    )


def _read_records(path: Path, plan: IngestionPlan) -> list[dict[str, str]]:
    fmt = detect_format(path)
    if plan.format != fmt:
        raise IngestionError(f"映射方案是 {plan.format}，但文件实际是 {fmt}")
    if fmt == "csv":
        return _read_csv_records(path)
    if fmt == "json":
        return _read_json_records(path, plan)
    return _read_xlsx_records(path, plan)


def _read_csv_records(path: Path) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    return [{key: ("" if value is None else value) for key, value in row.items()} for row in reader]


def _read_json_records(path: Path, plan: IngestionPlan) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if plan.records_path:
        for part in plan.records_path.split("."):
            if not isinstance(payload, dict) or part not in payload:
                raise IngestionError(f"JSON 路径不存在：{plan.records_path}")
            payload = payload[part]
    records, _ = _locate_records(payload if isinstance(payload, list) else payload)
    return [
        {key: _stringify(record.get(key)) for key in record}
        for record in records
        if isinstance(record, dict)
    ]


def _read_xlsx_records(path: Path, plan: IngestionPlan) -> list[dict[str, str]]:
    _sheets, rows = _read_xlsx(path, plan.sheet)
    if plan.sheet and not rows:
        raise IngestionError(f"工作表不存在或为空：{plan.sheet}")
    if not rows:
        raise IngestionError("XLSX 没有数据")
    header = rows[0]
    header_like = bool(header) and all(
        cell.strip() and _parse_date(cell) is None and not _is_number(cell)
        for cell in header
        if cell.strip()
    )
    data_rows = rows[1:] if header_like else rows
    wanted = {plan.date_field, plan.metric_field, plan.value_field}
    records: list[dict[str, str]] = []
    for row in data_rows:
        record: dict[str, str] = {}
        for index, cell in enumerate(row):
            name = _column_name(index)
            if name in wanted or not wanted:
                record[name] = cell
        records.append(record)
    return records


def _read_xlsx(path: Path, sheet: str) -> tuple[list[str], list[list[str]]]:
    """Minimal XLSX reader: workbook sheets, shared strings, and cell values as text."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise IngestionError("XLSX 文件无法读取（不是有效的 zip 结构）") from error
    with archive:
        try:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        except (KeyError, ET.ParseError) as error:
            raise IngestionError("XLSX 结构不完整，无法解析工作表") from error
        targets = {
            relation.attrib.get("Id"): relation.attrib.get("Target", "")
            for relation in rels
        }
        sheets: list[str] = []
        sheet_targets: dict[str, str] = {}
        for element in workbook.iter(f"{_NS_MAIN}sheet"):
            name = element.attrib.get("name", "")
            rel_id = element.attrib.get(f"{_NS_REL}id", "")
            sheets.append(name)
            target = targets.get(rel_id, "")
            if target and not target.startswith("/"):
                target = f"xl/{target}"
            sheet_targets[name] = target.lstrip("/")
        wanted = sheet if sheet else (sheets[0] if sheets else "")
        if wanted not in sheet_targets:
            raise IngestionError(f"工作表不存在：{wanted or '(空)'}")
        target = sheet_targets[wanted]
        if target not in archive.namelist():
            raise IngestionError("工作表文件缺失，无法读取")
        shared = _read_shared_strings(archive)
        sheet_xml = ET.fromstring(archive.read(target))
        rows: list[list[str]] = []
        for row_element in sheet_xml.iter(f"{_NS_MAIN}row"):
            cells: dict[int, str] = {}
            for cell in row_element.iter(f"{_NS_MAIN}c"):
                reference = cell.attrib.get("r", "")
                column_index = _column_index(reference)
                value_element = cell.find(f"{_NS_MAIN}v")
                text = value_element.text if value_element is not None else ""
                if cell.attrib.get("t") == "s" and text:
                    index = int(text)
                    text = shared[index] if 0 <= index < len(shared) else ""
                elif cell.attrib.get("t") == "inlineStr":
                    inline = cell.find(f"{_NS_MAIN}is")
                    text = "".join(
                        node.text or "" for node in inline.iter(f"{_NS_MAIN}t")
                    ) if inline is not None else ""
                if text is None:
                    text = ""
                cells[column_index] = text
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(index, "") for index in range(width)])
        return sheets, rows


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for si in root.iter(f"{_NS_MAIN}si"):
        strings.append("".join(node.text or "" for node in si.iter(f"{_NS_MAIN}t")))
    return strings


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        return 0
    index = 0
    for char in letters.group(0):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _column_name(index: int) -> str:
    name = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _match_field(lookup: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in lookup:
            return lookup[key]
    for lowered, original in lookup.items():
        for key in keys:
            if key in lowered:
                return original
    return None


def _parse_date(raw: str, hint: str = "") -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    if hint:
        try:
            return datetime.strptime(raw, hint).date()
        except ValueError:
            pass
    try:
        return date.fromisoformat(raw)
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    if _is_number(raw):
        serial = float(raw)
        if 20000 <= serial <= 80000:
            return _EXCEL_EPOCH + timedelta(days=int(serial))
    return None


def _is_number(raw: str) -> bool:
    try:
        float(raw.replace(",", ""))
    except (ValueError, TypeError):
        return False
    return True


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)
