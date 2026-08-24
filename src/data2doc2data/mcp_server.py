"""Minimal Model Context Protocol (MCP) tool server over stdio.

Exposes the deterministic evidence engine as callable tools so any MCP-capable
harness (WorkBuddy, DeepSeek harness, Codex, or a generic client) can invoke
``analyze``, ``check_rules``, and ``source_profile`` without a CLI adapter.

The transport is newline-delimited JSON-RPC 2.0 on stdin/stdout. The server is
zero-dependency, deterministic, and never writes raw CSV rows to the client:
tool results carry only derived signal, provenance, and source counts.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import TextIO

from .analysis import InputValidationError, analyze
from .artifacts import ArtifactStore
from .config import Profile, ProfileError, ProfileStore
from .cycle_runner import DemoCycleRunner
from .evidence_context import build_source_profile
from .rules import load_ruleset
from .reporting import build_html_report_from_cycle, safe_report_filename, write_html_report
from .workbench_api import WorkbenchApiError, WorkbenchService
from .workspace_store import WorkspaceStore, WorkspaceStoreError

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "data2doc2data"
SERVER_VERSION = "3.0.0"

TOOL_DEFS = (
    {
        "name": "analyze",
        "description": (
            "对本地 CSV 与决策文档运行确定性 Data-to-Doc-to-Data 证据分析，"
            "返回数据信号、文档语境、验证状态、证据链与限制条件。原始数据不离开本机。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "要回答的业务问题。"},
                "metric": {
                    "type": "string",
                    "description": "可选：显式指定指标名（如 retention_rate），避免歧义。",
                },
                "rules_path": {
                    "type": "string",
                    "description": "可选：声明式验证规则 JSON 文件的绝对路径。",
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "check_rules",
        "description": "校验声明式验证规则 JSON 文件，返回其中的指标与命名规则清单。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rules_path": {"type": "string", "description": "规则 JSON 文件的绝对路径。"},
            },
            "required": ["rules_path"],
        },
    },
    {
        "name": "source_profile",
        "description": ("返回当前工作区的本地数据画像（记录数、指标、日期范围、文档数），不含任何原始数据行。"),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "generate_html_report",
        "description": (
            "为本地工作台任务生成可离线打开的单文件 HTML 报告。报告写入受控 reports 目录，"
            "返回 SHA-256、MIME 类型与本地资源链接。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "要交付的工作台任务 ID。"},
                "filename": {"type": "string", "description": "可选的报告文件名；目录部分会被忽略。"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "run_analysis_cycle",
        "description": "运行最多三轮的本地业务诊断循环；原始数据不进入 MCP 返回值。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "data_path": {"type": "string"},
                "document_paths": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task_id", "data_path"],
        },
    },
    {
        "name": "list_cycle_artifacts",
        "description": "列出分析循环的本地产物标识与方法摘要，不返回原始记录或本地路径。",
        "inputSchema": {
            "type": "object",
            "properties": {"cycle_id": {"type": "string"}},
            "required": ["cycle_id"],
        },
    },
    {
        "name": "generate_cycle_html_report",
        "description": "从持久化分析循环生成单文件离线 HTML 报告。",
        "inputSchema": {
            "type": "object",
            "properties": {"cycle_id": {"type": "string"}, "filename": {"type": "string"}},
            "required": ["cycle_id"],
        },
    },
)
TOOL_NAMES = {tool["name"] for tool in TOOL_DEFS}


class ProtocolError(Exception):
    """A JSON-RPC protocol error, distinct from a tool execution error."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def serve(store: ProfileStore, stdin: TextIO | None = None, stdout: TextIO | None = None) -> None:
    """Run the read-eval-print loop until the input stream closes."""
    input_stream = stdin if stdin is not None else sys.stdin
    output_stream = stdout if stdout is not None else sys.stdout
    for line in input_stream:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            message = json.loads(stripped)
        except json.JSONDecodeError:
            _write(output_stream, _error(None, -32700, "Parse error"))
            continue
        response = handle_message(message, store)
        if response is not None:
            _write(output_stream, response)


def handle_message(message: object, store: ProfileStore) -> dict[str, object] | None:
    """Dispatch a single decoded JSON-RPC message and return a response, if any."""
    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid Request")
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None  # notifications and responses are not answered by a server
    if not isinstance(method, str):
        return _error(request_id, -32600, "Invalid Request")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(request_id, -32602, "Invalid params")
    try:
        if method == "initialize":
            return _response(request_id, _initialize())
        if method == "tools/list":
            return _response(request_id, {"tools": list(TOOL_DEFS)})
        if method == "tools/call":
            return _response(request_id, _call_tool(params, store))
        if method == "ping":
            return _response(request_id, {})
        return _error(request_id, -32601, "Method not found")
    except ProtocolError as error:
        return _error(request_id, error.code, str(error))


def _initialize() -> dict[str, object]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def _call_tool(params: dict[str, object], store: ProfileStore) -> dict[str, object]:
    name = params.get("name")
    arguments = params.get("arguments")
    if not isinstance(name, str) or name not in TOOL_NAMES:
        raise ProtocolError(-32602, f"Unknown tool: {name!r}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ProtocolError(-32602, "tool arguments must be an object")
    try:
        if name == "analyze":
            return _analyze_tool(arguments, store)
        if name == "check_rules":
            return _check_rules_tool(arguments)
        if name == "generate_html_report":
            return _generate_html_report_tool(arguments, store)
        if name == "run_analysis_cycle":
            return _run_analysis_cycle_tool(arguments, store)
        if name == "list_cycle_artifacts":
            return _list_cycle_artifacts_tool(arguments, store)
        if name == "generate_cycle_html_report":
            return _generate_cycle_html_report_tool(arguments, store)
        return _source_profile_tool(store)
    except (InputValidationError, ProfileError, WorkspaceStoreError, WorkbenchApiError, OSError, ValueError) as error:
        return {"content": [{"type": "text", "text": str(error)}], "isError": True}


def _analyze_tool(arguments: dict[str, object], store: ProfileStore) -> dict[str, object]:
    question = arguments.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ProtocolError(-32602, "question must be a non-empty string")
    metric = arguments.get("metric")
    rules_path = arguments.get("rules_path")
    if metric is not None and not isinstance(metric, str):
        raise ProtocolError(-32602, "metric must be a string")
    if rules_path is not None and not isinstance(rules_path, str):
        raise ProtocolError(-32602, "rules_path must be a string")

    profile = store.load() or Profile.demo()
    ruleset = load_ruleset(Path(rules_path)) if rules_path else None
    result = analyze(question.strip(), profile, metric or None, store.index_cache_path, ruleset)
    text = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def _check_rules_tool(arguments: dict[str, object]) -> dict[str, object]:
    rules_path = arguments.get("rules_path")
    if not isinstance(rules_path, str) or not rules_path.strip():
        raise ProtocolError(-32602, "rules_path must be a non-empty string")
    ruleset = load_ruleset(Path(rules_path))
    payload = {
        "valid": True,
        "metrics": sorted(ruleset.metrics),
        "rules": [rule.rule_id for rule in ruleset.rules],
    }
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}


def _source_profile_tool(store: ProfileStore) -> dict[str, object]:
    profile = store.load() or Profile.demo()
    source_profile = build_source_profile(profile)
    text = json.dumps(source_profile.to_dict(), ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def _generate_html_report_tool(arguments: dict[str, object], store: ProfileStore) -> dict[str, object]:
    task_id = arguments.get("task_id")
    filename = arguments.get("filename")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProtocolError(-32602, "task_id must be a non-empty string")
    if filename is not None and not isinstance(filename, str):
        raise ProtocolError(-32602, "filename must be a string")
    workspace = WorkspaceStore(store.workspace_database_path)
    artifact = WorkbenchService(workspace).local_task_report(task_id.strip())
    approved_root = store.path.parent.expanduser().resolve() / "reports"
    safe_name = safe_report_filename(filename or artifact.filename, artifact.filename)
    path, digest = write_html_report(artifact, approved_root / safe_name)
    payload = {
        "task_id": task_id.strip(),
        "filename": path.name,
        "mime_type": "text/html; charset=utf-8",
        "byte_count": path.stat().st_size,
        "sha256": digest,
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)},
            {
                "type": "resource_link",
                "name": path.name,
                "title": "Data2Doc2Data HTML report",
                "uri": path.as_uri(),
                "mimeType": "text/html",
                "size": path.stat().st_size,
            },
        ]
    }


def _run_analysis_cycle_tool(arguments: dict[str, object], store: ProfileStore) -> dict[str, object]:
    task_id = arguments.get("task_id")
    data_path = arguments.get("data_path")
    document_paths = arguments.get("document_paths", [])
    if not isinstance(task_id, str) or not task_id.strip():
        raise ProtocolError(-32602, "task_id must be a non-empty string")
    if not isinstance(data_path, str) or not data_path.strip():
        raise ProtocolError(-32602, "data_path must be a non-empty string")
    if not isinstance(document_paths, list) or any(not isinstance(path, str) for path in document_paths):
        raise ProtocolError(-32602, "document_paths must be a list of strings")
    workspace = WorkspaceStore(store.workspace_database_path)
    task = workspace.get_task(task_id.strip())
    if task is None:
        raise WorkspaceStoreError("task not found")
    result = DemoCycleRunner(workspace).run(task, Path(data_path), tuple(Path(path) for path in document_paths))
    payload = {"cycle": result.cycle.to_dict(), "artifact_refs": list(result.cycle.artifact_refs)}
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]}


def _list_cycle_artifacts_tool(arguments: dict[str, object], store: ProfileStore) -> dict[str, object]:
    cycle_id = arguments.get("cycle_id")
    if not isinstance(cycle_id, str) or not cycle_id.strip():
        raise ProtocolError(-32602, "cycle_id must be a non-empty string")
    workspace = WorkspaceStore(store.workspace_database_path)
    cycle = workspace.get_analysis_cycle(cycle_id.strip())
    if cycle is None:
        raise WorkspaceStoreError("analysis cycle not found")
    artifacts = ArtifactStore(workspace.path.parent / "artifacts")
    items = []
    for artifact_ref in cycle.artifact_refs:
        record = artifacts.load(artifact_ref)
        payload = record.get("payload", {})
        items.append(
            {
                "artifact_ref": artifact_ref,
                "kind": record.get("kind"),
                "method": payload.get("method") if isinstance(payload, dict) else None,
                "status": payload.get("status") if isinstance(payload, dict) else None,
            }
        )
    return {"content": [{"type": "text", "text": json.dumps({"artifacts": items}, ensure_ascii=False, indent=2)}]}


def _generate_cycle_html_report_tool(arguments: dict[str, object], store: ProfileStore) -> dict[str, object]:
    cycle_id = arguments.get("cycle_id")
    filename = arguments.get("filename")
    if not isinstance(cycle_id, str) or not cycle_id.strip():
        raise ProtocolError(-32602, "cycle_id must be a non-empty string")
    if filename is not None and not isinstance(filename, str):
        raise ProtocolError(-32602, "filename must be a string")
    workspace = WorkspaceStore(store.workspace_database_path)
    cycle = workspace.get_analysis_cycle(cycle_id.strip())
    if cycle is None:
        raise WorkspaceStoreError("analysis cycle not found")
    context = workspace.get_analysis_cycle_context(cycle.cycle_id)
    task = workspace.get_task(str(context.get("task_id", "")))
    if task is None:
        raise WorkspaceStoreError("analysis cycle task not found")
    artifact = build_html_report_from_cycle(task, cycle, ArtifactStore(workspace.path.parent / "artifacts"))
    approved_root = store.path.parent.expanduser().resolve() / "reports"
    safe_name = safe_report_filename(filename or artifact.filename, artifact.filename)
    path, digest = write_html_report(artifact, approved_root / safe_name)
    payload = {
        "cycle_id": cycle.cycle_id,
        "filename": path.name,
        "mime_type": "text/html; charset=utf-8",
        "byte_count": path.stat().st_size,
        "sha256": digest,
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)},
            {
                "type": "resource_link",
                "name": path.name,
                "title": "Data2Doc2Data cycle HTML report",
                "uri": path.as_uri(),
                "mimeType": "text/html",
                "size": path.stat().st_size,
            },
        ]
    }


def _response(request_id: object, result: object) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object | None, code: int, message: str) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _write(stream: TextIO, message: dict[str, object]) -> None:
    stream.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()
