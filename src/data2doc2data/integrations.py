"""Self-contained MCP host templates and a read-only integration doctor."""

from __future__ import annotations

from importlib.resources import files
import json
import tomllib
from typing import Mapping

from .config import ProfileStore
from .flagship_cases import FlagshipCaseCatalog
from .mcp_server import PROTOCOL_VERSION, TOOL_NAMES, handle_message


TEMPLATE_FILES = {
    "codex": "codex-config.toml",
    "deepseek-harness": "deepseek-harness.cordis.yml",
    "codebuddy": "codebuddy.mcp.json",
}


def load_host_templates() -> dict[str, str]:
    root = files("data2doc2data").joinpath("integration_templates")
    return {host: root.joinpath(filename).read_text(encoding="utf-8") for host, filename in TEMPLATE_FILES.items()}


def validate_host_templates(templates: Mapping[str, str] | None = None) -> bool:
    values = dict(templates or load_host_templates())
    if set(values) != set(TEMPLATE_FILES):
        return False
    if any(marker in text for text in values.values() for marker in ("API_KEY", "Bearer ", "/Users/")):
        return False
    try:
        codex = tomllib.loads(values["codex"])["mcp_servers"]["data2doc2data"]
        codebuddy = json.loads(values["codebuddy"])["mcpServers"]["data2doc2data"]
    except (KeyError, TypeError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return False
    if codex.get("command") != "data2doc2data" or codex.get("args") != ["mcp"]:
        return False
    if codebuddy.get("type") != "stdio" or codebuddy.get("command") != "data2doc2data":
        return False
    if codebuddy.get("args") != ["mcp"]:
        return False
    harness = values["deepseek-harness"]
    required_lines = (
        "name: '@deepseek-ai/dsh-mcp-client'",
        "serverName: data2doc2data",
        "transport: stdio",
        "command: data2doc2data",
        "args: ['mcp']",
    )
    return all(line in harness for line in required_lines)


def run_doctor(store: ProfileStore) -> dict[str, object]:
    """Exercise local contracts without starting a host process or exposing paths."""
    checks: list[dict[str, object]] = []

    try:
        catalog = FlagshipCaseCatalog.load()
        cases = catalog.list()
        checks.append(
            {
                "id": "flagship_cases",
                "ok": len(cases) == 2,
                "case_count": len(cases),
                "record_count": sum(case.record_count for case in cases),
                "document_count": sum(case.document_count for case in cases),
            }
        )
    except Exception as error:  # pragma: no cover - defensive diagnostics boundary
        checks.append({"id": "flagship_cases", "ok": False, "error": type(error).__name__})

    try:
        initialized = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION},
            },
            store,
        )
        listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, store)
        init_result = initialized.get("result", {}) if isinstance(initialized, dict) else {}
        tools_result = listed.get("result", {}) if isinstance(listed, dict) else {}
        tools = tools_result.get("tools", []) if isinstance(tools_result, dict) else []
        tool_names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
        checks.append(
            {
                "id": "mcp_protocol",
                "ok": init_result.get("protocolVersion") == PROTOCOL_VERSION and tool_names == TOOL_NAMES,
                "protocol_version": init_result.get("protocolVersion"),
                "tool_count": len(tools),
                "tools": sorted(name for name in tool_names if isinstance(name, str)),
            }
        )
    except Exception as error:  # pragma: no cover - defensive diagnostics boundary
        checks.append({"id": "mcp_protocol", "ok": False, "error": type(error).__name__})

    try:
        response = handle_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "source_profile", "arguments": {}},
            },
            store,
        )
        result = response.get("result", {}) if isinstance(response, dict) else {}
        content = result.get("content", []) if isinstance(result, dict) else []
        first = content[0] if isinstance(content, list) and content else {}
        profile = json.loads(first.get("text", "{}")) if isinstance(first, dict) else {}
        checks.append(
            {
                "id": "source_profile",
                "ok": isinstance(profile.get("record_count"), int) and profile["record_count"] > 0,
                "mode": profile.get("mode"),
                "synthetic": profile.get("synthetic"),
                "record_count": profile.get("record_count", 0),
                "metric_count": len(profile.get("metrics", [])),
                "document_count": profile.get("document_count", 0),
            }
        )
    except Exception as error:  # pragma: no cover - defensive diagnostics boundary
        checks.append({"id": "source_profile", "ok": False, "error": type(error).__name__})

    try:
        templates = load_host_templates()
        valid = validate_host_templates(templates)
        checks.append(
            {
                "id": "host_templates",
                "ok": valid,
                "host_count": len(templates),
                "hosts": sorted(templates),
            }
        )
    except Exception as error:  # pragma: no cover - defensive diagnostics boundary
        checks.append({"id": "host_templates", "ok": False, "error": type(error).__name__})

    return {
        "product": "data2doc2data",
        "ok": all(check.get("ok") is True for check in checks),
        "checks": checks,
    }
