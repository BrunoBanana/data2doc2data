"""Standalone, source-backed HTML reports for workbench tasks."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from typing import Any, Mapping, Sequence

from .analysis_cycle import AnalysisCycle
from .artifacts import ArtifactStore
from .evidence_graph import build_cycle_evidence_graph
from .workspace import AnalysisTask


@dataclass(frozen=True)
class HtmlReportArtifact:
    filename: str
    html: str


def safe_report_filename(value: str, fallback: str = "analysis-report.html") -> str:
    """Return a bounded leaf filename suitable for an approved report directory."""
    leaf = Path(value).name
    normalized = unicodedata.normalize("NFKD", leaf).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._")[:100]
    if not stem:
        stem = Path(fallback).stem
    if stem.lower().endswith(".html"):
        return stem
    return f"{stem}.html"


def write_html_report(artifact: HtmlReportArtifact, output: Path) -> tuple[Path, str]:
    """Atomically write a standalone report and return its path and SHA-256 digest."""
    import hashlib

    target = output.expanduser().resolve()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = artifact.html.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
    ) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    return target, digest


def build_html_report(
    task: AnalysisTask,
    dashboard: Mapping[str, Any] | None,
    text_dashboard: Mapping[str, Any] | None,
    evidence_graph: Mapping[str, Any] | None,
    *,
    run_count: int,
) -> HtmlReportArtifact:
    blocks = _list(dashboard, "blocks")
    kpis = [block for block in blocks if block.get("kind") == "kpi"]
    findings = [block for block in blocks if block.get("kind") != "kpi"]
    claims = _list(text_dashboard, "claims")
    nodes = _list(evidence_graph, "nodes")
    documents = _integer(text_dashboard, "document_count")
    failures = _integer(text_dashboard, "failure_count")
    pending = sum(node.get("status") in {"pending", "insufficient"} for node in nodes) + sum(
        claim.get("status") == "pending" for claim in claims
    )
    summary = _executive_summary(kpis, documents, claims, nodes, run_count)
    body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>{escape(task.title)} · Data2Doc2Data 分析报告</title><style>{_STYLES}</style></head>
<body><main>
<header class="report-header"><p class="eyebrow">DATA2DOC2DATA · LOCAL ANALYSIS REPORT</p><h1>{escape(task.title)}</h1><p class="goal">{escape(task.goal)}</p><div class="meta"><span>任务 {escape(task.task_id)}</span><span>{len(task.snapshot_refs)} 项锁定资产</span><span>{run_count} 次运行</span></div></header>
<section class="executive"><p class="eyebrow">DECISION BRIEF</p><h2>分析结论</h2><ul>{"".join(f"<li>{item}</li>" for item in summary)}</ul></section>
{_verification_strip(nodes)}
{_kpi_strip(kpis)}
<section><h2>关键发现</h2>{_findings(findings, dashboard is not None)}</section>
{_text_findings(text_dashboard, claims)}
{_evidence_findings(nodes, evidence_graph)}
<section><h2>推荐下一步</h2><ol>{_recommendations(pending, failures, bool(dashboard), bool(text_dashboard))}</ol></section>
<section><h2>仍需回答的问题</h2><ul>{_questions(claims, nodes)}</ul></section>
<section><h2>局限与假设</h2><ul><li>报告只使用本机锁定快照生成；模型建议不会覆盖确定性计算结果。</li><li>文本中的主张在获得数据或独立证据核验前保持“待核验”。</li><li>图表展示有界聚合结果，不包含原始记录、凭据或本地文件路径。</li></ul></section>
<section class="sources"><h2>来源与计算口径</h2>{_sources(task, blocks, claims)}</section>
</main><footer>由 Data2Doc2Data 本地工作台生成 · 单文件 HTML · 可离线打开与打印</footer></body></html>"""
    return HtmlReportArtifact(f"data2doc2data-{task.task_id}.html", body)


def build_html_report_from_cycle(
    task: AnalysisTask,
    cycle: AnalysisCycle,
    artifact_store: ArtifactStore,
    *,
    run_count: int = 1,
) -> HtmlReportArtifact:
    """Build the same standalone report contract directly from persisted artifacts."""
    graph = build_cycle_evidence_graph(cycle, artifact_store)
    base = build_html_report(task, None, None, graph.to_dict(), run_count=run_count)
    cards = []
    for index, artifact_ref in enumerate(cycle.artifact_refs, 1):
        record = artifact_store.load(artifact_ref)
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        method = escape(str(payload.get("method", record.get("kind", "artifact"))))
        status = escape(str(payload.get("status", "completed")))
        summary = escape(str(payload.get("summary", "已生成本地产物。")))
        sample_size = escape(str(payload.get("sample_size", len(payload.get("topics", [])))))
        parameters = payload.get("parameters", {})
        parameter_text = escape(
            ", ".join(f"{key}={value}" for key, value in parameters.items())
            if isinstance(parameters, Mapping)
            else ""
        )
        limitations = payload.get("limitations", [])
        limitation_html = "".join(f"<li>{escape(str(item))}</li>" for item in limitations if str(item).strip())
        word_cloud = _safe_embedded_svg(payload.get("word_cloud_svg"))
        cards.append(
            f'<article class="finding"><p class="eyebrow">ROUND ARTIFACT {index}</p>'
            f"<h3>{method}</h3><p>{summary}</p>"
            f'<div class="meta"><span>状态 {status}</span><span>样本 {sample_size}</span>'
            f"<span>产物 {escape(artifact_ref)}</span></div>"
            f"<p><strong>参数与方法：</strong>{parameter_text or method}</p>"
            f"{word_cloud}<ul>{limitation_html or '<li>未声明额外限制。</li>'}</ul></article>"
        )
    section = (
        '<section><p class="eyebrow">AUDITABLE METHODS</p><h2>分析方法、产物与限制</h2>'
        + ("".join(cards) or "<p>当前循环尚未形成可交付产物。</p>")
        + "</section>"
    )
    marker = "<section><h2>推荐下一步</h2>"
    html = base.html.replace(marker, section + marker, 1)
    return HtmlReportArtifact(base.filename, html)


def _safe_embedded_svg(value: object) -> str:
    if not isinstance(value, str):
        return ""
    lowered = value.lower()
    if not value.lstrip().startswith("<svg") or "<script" in lowered or "http" in lowered or "javascript:" in lowered:
        return ""
    return value


def _executive_summary(
    kpis: Sequence[Mapping[str, Any]],
    documents: int,
    claims: Sequence[Mapping[str, Any]],
    nodes: Sequence[Mapping[str, Any]],
    run_count: int,
) -> list[str]:
    values = {str(block.get("title")): block.get("value") for block in kpis}
    if values:
        headline = "，".join(
            f"{escape(label)}为 <strong>{escape(str(value))}</strong>" for label, value in list(values.items())[:4]
        )
        first = f"<strong>当前数据底盘已形成。</strong> {headline}。"
    else:
        first = "<strong>尚无可量化结论。</strong> 当前任务尚未接入可分析的数据快照。"
    second = (
        f"<strong>文本材料仍需核验。</strong> 已纳入 {documents} 份文档并识别 {len(claims)} 条主张；主张不会自动升级为数据事实。"
        if documents
        else "<strong>文本材料尚未纳入。</strong> 可选地导入 Markdown/TXT，以补充策略、访谈或业务说明。"
    )
    statuses: dict[str, int] = {}
    for node in nodes:
        status = str(node.get("status", "pending"))
        statuses[status] = statuses.get(status, 0) + 1
    labels = {
        "verified": "已验证",
        "supported": "支持",
        "contradicted": "存在冲突",
        "insufficient": "证据不足",
        "pending": "待验证",
    }
    status_text = (
        "、".join(f"{escape(labels.get(key, key))} {value}" for key, value in sorted(statuses.items())) or "尚未生成"
    )
    third = f"<strong>证据过程可审计。</strong> 已保存 {run_count} 次运行；当前证据状态为 {status_text}。"
    return [first, second, third]


def _kpi_strip(kpis: Sequence[Mapping[str, Any]]) -> str:
    if not kpis:
        return ""
    cards = "".join(
        f'<article class="kpi"><span>{escape(str(block.get("title", "指标")))}</span><strong>{escape(str(block.get("value", "—")))}</strong>{_provenance(block)}</article>'
        for block in kpis[:8]
    )
    return f'<section class="kpi-strip" aria-label="核心指标">{cards}</section>'


def _verification_strip(nodes: Sequence[Mapping[str, Any]]) -> str:
    verified = sum(node.get("status") in {"verified", "supported"} for node in nodes)
    conflicted = sum(node.get("status") in {"contradicted", "conflicted"} for node in nodes)
    pending = max(0, len(nodes) - verified - conflicted)
    return (
        '<section class="verification" aria-label="证据验证">'
        "<div><span>证据验证</span><strong>可审计状态</strong></div>"
        f"<div><span>已验证</span><strong>{verified}</strong></div>"
        f"<div><span>待验证</span><strong>{pending}</strong></div>"
        f"<div><span>存在冲突</span><strong>{conflicted}</strong></div>"
        "</section>"
    )


def _findings(findings: Sequence[Mapping[str, Any]], has_dashboard: bool) -> str:
    if not has_dashboard:
        return '<article class="empty"><strong>当前任务尚未接入可分析的数据快照。</strong><p>导入数据后，这里会展示数据画像、趋势和分布。</p></article>'
    if not findings:
        return '<article class="empty"><strong>暂无可视化区块。</strong></article>'
    rendered = []
    for block in findings:
        title = escape(str(block.get("title", "分析结果")))
        if block.get("kind") == "chart":
            visual = _chart_svg(block)
        else:
            visual = _table(block.get("data"))
        rendered.append(
            f'<article class="finding"><h3>{title}</h3><p>该区块基于锁定快照的有界聚合结果，用于识别变化范围并支持后续调查。</p>{visual}{_provenance(block)}</article>'
        )
    return "".join(rendered)


def _chart_svg(block: Mapping[str, Any]) -> str:
    chart = block.get("chart")
    data = block.get("data")
    if not isinstance(chart, Mapping) or not isinstance(data, list) or not data:
        return '<p class="empty">无可绘制数据</p>'
    encoding = chart.get("encoding")
    if not isinstance(encoding, Mapping):
        return _table(data)
    x_field = _field(encoding, "x")
    y_field = _field(encoding, "y")
    color_field = _field(encoding, "color")
    if not x_field or not y_field:
        return _table(data)
    points = []
    for row in data[:200]:
        if not isinstance(row, Mapping):
            continue
        try:
            value = float(row.get(y_field))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            points.append(
                (str(row.get(x_field, "")), str(row.get(color_field, "全部")) if color_field else "全部", value)
            )
    if not points:
        return _table(data)
    x_values = list(dict.fromkeys(point[0] for point in points))
    y_values = [point[2] for point in points]
    low, high = min(y_values), max(y_values)
    span = high - low or 1.0
    palette = ("#08a854", "#151511", "#c36b00", "#6c50a3", "#bd3434", "#277d88")
    groups = list(dict.fromkeys(point[1] for point in points))
    lines = []
    legend = []
    for group_index, group in enumerate(groups[:12]):
        group_points = [point for point in points if point[1] == group]
        coords = []
        for x_value, _, value in group_points:
            x_index = x_values.index(x_value)
            x = 56 + (x_index / max(1, len(x_values) - 1)) * 620
            y = 210 - ((value - low) / span) * 160
            coords.append((x, y))
        color = palette[group_index % len(palette)]
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        lines.append(
            f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        )
        lines.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>' for x, y in coords)
        legend.append(f'<span><i style="background:{color}"></i>{escape(group)}</span>')
    labels = "".join(
        f'<text x="{56 + (index / max(1, len(x_values) - 1)) * 620:.1f}" y="235" text-anchor="middle">{escape(label[:14])}</text>'
        for index, label in enumerate(x_values)
    )
    svg = f'<svg class="chart" viewBox="0 0 720 250" role="img" aria-label="{escape(str(block.get("title", "趋势图")))}"><line x1="56" y1="30" x2="56" y2="210"/><line x1="56" y1="210" x2="686" y2="210"/><text x="8" y="38">{high:.4g}</text><text x="8" y="210">{low:.4g}</text>{"".join(lines)}{labels}</svg>'
    return f'{svg}<div class="legend">{"".join(legend)}</div>'


def _table(value: object) -> str:
    rows = [row for row in value[:50] if isinstance(row, Mapping)] if isinstance(value, list) else []
    if not rows:
        return '<p class="empty">没有可展示的聚合记录</p>'
    fields = list(rows[0])[:12]
    head = "".join(f"<th>{escape(str(field))}</th>" for field in fields)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row.get(field, '')))}</td>" for field in fields) + "</tr>" for row in rows
    )
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _text_findings(text: Mapping[str, Any] | None, claims: Sequence[Mapping[str, Any]]) -> str:
    if not text:
        return '<section><h2>文本材料与主张</h2><article class="empty"><strong>未导入文本材料。</strong><p>这不会影响数据画像和确定性 Dashboard。</p></article></section>'
    topics = (
        "".join(f"<span>{escape(str(item))}</span>" for item in _values(text.get("topics")))
        or "<span>未识别主题</span>"
    )
    items = []
    for claim in claims[:100]:
        citation = claim.get("citation") if isinstance(claim.get("citation"), Mapping) else {}
        document = escape(str(citation.get("document", "未知文档")))
        start = escape(str(citation.get("start_line", "—")))
        end = escape(str(citation.get("end_line", "—")))
        items.append(
            f'<article class="claim"><span>{escape(str(claim.get("status", "pending")))}</span><p>{escape(str(claim.get("text", "")))}</p><small>{document} · 第 {start}–{end} 行</small></article>'
        )
    claims_html = "".join(items) or '<p class="empty">未抽取到显式主张</p>'
    return f'<section><h2>文本材料与主张</h2><div class="tags">{topics}</div><div class="claims">{claims_html}</div></section>'


def _evidence_findings(nodes: Sequence[Mapping[str, Any]], graph: Mapping[str, Any] | None) -> str:
    if not graph:
        return '<section><h2>证据与假设</h2><article class="empty"><strong>尚未运行可观察分析。</strong></article></section>'
    rows = "".join(
        f"<tr><td>{escape(str(node.get('kind', '')))}</td><td>{escape(str(node.get('label', '')))}</td><td>{escape(str(node.get('status', '')))}</td><td>{escape(str(node.get('artifact_ref') or '—'))}</td></tr>"
        for node in nodes[:200]
    )
    return f'<section><h2>证据与假设</h2><p>图谱包含 {len(nodes)} 个节点与 {len(_list(graph, "edges"))} 条显式关系；下表只显示可审计状态。</p><div class="table-wrap"><table><thead><tr><th>类型</th><th>内容</th><th>状态</th><th>制品</th></tr></thead><tbody>{rows}</tbody></table></div></section>'


def _recommendations(pending: int, failures: int, has_dashboard: bool, has_text: bool) -> str:
    items = []
    if not has_dashboard:
        items.append("接入并锁定业务数据快照，先生成可重复的数据画像。")
    if pending:
        items.append(f"优先核验 {pending} 项待定或证据不足内容，并补充支持/反驳来源。")
    if failures:
        items.append(f"修复 {failures} 份文本材料的解析问题后重新生成报告。")
    if not has_text:
        items.append("如需对照策略或访谈结论，导入带有明确标题和主张的 Markdown/TXT。")
    items.append("围绕影响最大的异常建立负责人、截止时间和复核指标，再创建新运行。")
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _questions(claims: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]]) -> str:
    questions = []
    if claims:
        questions.append("哪些文本主张能够由当前数据直接支持，哪些需要新增数据源？")
    if any(node.get("status") == "insufficient" for node in nodes):
        questions.append("证据不足的假设需要哪些分群、时间窗口或外部证据才能区分？")
    questions.append("当前变化是否由数据质量、口径变化或真实业务行为驱动？")
    return "".join(f"<li>{escape(item)}</li>" for item in questions)


def _sources(task: AnalysisTask, blocks: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]]) -> str:
    assets = (
        "".join(
            f"<li><strong>{escape(ref.kind)}</strong> · {escape(ref.snapshot_id)} · SHA-256 {escape(ref.sha256)}</li>"
            for ref in task.snapshot_refs
        )
        or "<li>暂无锁定资产</li>"
    )
    calculations = "".join(_provenance(block, expanded=False) for block in blocks)
    documents = "".join(
        f"<li>{escape(str((claim.get('citation') or {}).get('document', '未知文档')))}</li>"
        for claim in claims
        if isinstance(claim.get("citation"), Mapping)
    )
    return f"<h3>锁定资产</h3><ul>{assets}</ul><h3>计算口径</h3>{calculations or '<p>暂无计算口径</p>'}<h3>文档引用</h3><ul>{documents or '<li>暂无文档引用</li>'}</ul>"


def _provenance(block: Mapping[str, Any], expanded: bool = False) -> str:
    provenance = block.get("provenance")
    if not isinstance(provenance, Mapping):
        return ""
    open_attr = " open" if expanded else ""
    return f"<details{open_attr}><summary>查看计算依据</summary><dl><dt>表达式</dt><dd>{escape(str(provenance.get('expression', '')))}</dd><dt>字段</dt><dd>{escape('、'.join(str(item) for item in _values(provenance.get('fields'))))}</dd><dt>快照</dt><dd>{escape(str(provenance.get('snapshot_id', '')))}</dd><dt>结果行数</dt><dd>{escape(str(provenance.get('result_row_count', '')))}</dd></dl></details>"


def _list(value: Mapping[str, Any] | None, key: str) -> list[Mapping[str, Any]]:
    raw = value.get(key) if isinstance(value, Mapping) else None
    return [item for item in raw if isinstance(item, Mapping)] if isinstance(raw, list) else []


def _values(value: object) -> list[object]:
    return value[:100] if isinstance(value, list) else []


def _integer(value: Mapping[str, Any] | None, key: str) -> int:
    raw = value.get(key) if isinstance(value, Mapping) else 0
    return raw if isinstance(raw, int) and raw >= 0 else 0


def _field(encoding: Mapping[str, Any], channel: str) -> str:
    value = encoding.get(channel)
    return str(value.get("field")) if isinstance(value, Mapping) and isinstance(value.get("field"), str) else ""


_STYLES = """
:root{color-scheme:light;--paper:#f4f1e8;--sheet:#fffdf7;--ink:#151511;--muted:#6f6b60;--line:#151511;--line-soft:#d9d3c4;--signal:#08d36c;--signal-dark:#008e47;--warn:#9a5d0c;--danger:#b52e2e}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--paper);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{width:min(1080px,calc(100% - 32px));margin:32px auto;padding:52px;border:2px solid var(--line);background:var(--sheet);box-shadow:8px 8px 0 var(--signal)}h1{max-width:850px;margin:8px 0 10px;font-size:48px;line-height:1.02;letter-spacing:-.05em}h2{margin:42px 0 16px;padding-top:12px;border-top:2px solid var(--line);font-size:24px}h3{margin:20px 0 8px;font-size:18px}.eyebrow{margin:0;color:var(--signal-dark);font:800 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.12em}.goal{max-width:760px;color:var(--muted);font-size:18px}.meta,.legend,.tags{display:flex;flex-wrap:wrap;gap:8px}.meta span,.tags span{padding:5px 9px;border:1px solid var(--line);border-radius:2px;color:var(--ink);background:var(--paper);font-size:12px}.executive{margin-top:32px;padding:24px 28px;border:2px solid var(--line);background:#effff4;box-shadow:4px 4px 0 var(--ink)}.executive h2{margin:5px 0 12px;padding:0;border:0;font-size:30px}.executive li{margin:9px 0}.verification{display:grid;grid-template-columns:1.4fr repeat(3,1fr);margin:24px 0;border:2px solid var(--line)}.verification>div{display:grid;gap:4px;padding:14px 16px;border-left:1px solid var(--line)}.verification>div:first-child{border-left:0;background:var(--ink);color:var(--sheet)}.verification span{color:var(--muted);font-size:11px}.verification>div:first-child span{color:#c8c4b9}.verification strong{font-size:20px}.kpi-strip{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;margin:20px 0;border:1px solid var(--line)}.kpi{display:grid;gap:5px;padding:16px;border-left:1px solid var(--line)}.kpi:first-child{border-left:0}.kpi>span{color:var(--muted);font-size:12px}.kpi>strong{font-size:24px}.finding,.claim,.empty{margin:12px 0;padding:18px;border:1px solid var(--line);border-radius:2px;background:var(--sheet)}.finding{border-top:3px solid var(--signal)}.finding>p,.empty p{color:var(--muted)}.chart{width:100%;height:auto;margin:12px 0;background:var(--sheet)}.chart line{stroke:#8e897e;stroke-width:1}.chart text{fill:var(--muted);font-size:10px}.legend i{display:inline-block;width:8px;height:8px;margin-right:5px}.legend span{font-size:11px}.table-wrap{max-width:100%;overflow:auto;border:1px solid var(--line)}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:9px;border-bottom:1px solid var(--line-soft);text-align:left;vertical-align:top}th{color:var(--muted);background:#ece7db}details{margin-top:10px;color:var(--muted);font-size:11px}summary{cursor:pointer;color:var(--signal-dark);font-weight:700}dl{display:grid;grid-template-columns:90px 1fr;gap:5px;margin:8px 0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.claims{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.claim{margin:0}.claim>span{color:var(--warn);font-size:10px;text-transform:uppercase}.claim p{margin:7px 0}.claim small{color:var(--muted)}.sources{font-size:12px}footer{padding:18px;text-align:center;color:var(--muted);font-size:11px}@media(max-width:700px){main{width:100%;margin:0;padding:24px;border-width:0;box-shadow:none}h1{font-size:34px}.verification,.kpi-strip,.claims{grid-template-columns:1fr 1fr}.verification>div:nth-child(3){border-left:0;border-top:1px solid var(--line)}.verification>div:nth-child(4){border-top:1px solid var(--line)}}@media print{body{background:white}main{width:100%;margin:0;padding:12mm;border:0;box-shadow:none}details{display:block}section,.finding,.kpi{break-inside:avoid}.report-header{break-after:avoid}footer{display:none}}
"""
