# MCP Tool Server Design

**Date:** 2026-08-17

## Goal

Let any MCP-capable harness — WorkBuddy, DeepSeek harness, Codex, or a generic client — invoke the deterministic evidence engine as tools, instead of depending on the CLI adapter or the web workbench. This is the "plugin" surface for cross-harness distribution.

## Decision

- Add `mcp_server.py`, a minimal Model Context Protocol (MCP) server over the stdio transport (newline-delimited JSON-RPC 2.0).
- Expose exactly three tools:

  | Tool | Purpose |
  |---|---|
  | `analyze` | Run deterministic Data-to-Doc-to-Data analysis (`question`, optional `metric`, optional `rules_path`). |
  | `check_rules` | Validate a declarative rules JSON file and list its metrics and rules. |
  | `source_profile` | Return the local dataset profile (counts, metrics, dates, documents) without any raw rows. |

- Add `data2doc2data mcp` to the CLI; it reads `--config` (or the default profile store) and answers on stdin/stdout.

## Protocol scope

- Handshake: `initialize` returns `protocolVersion = "2024-11-05"`, `capabilities.tools`, and `serverInfo`.
- Discovery: `tools/list` returns the three tool definitions with JSON Schema `inputSchema`.
- Invocation: `tools/call` returns a `content` array of text items.
- `ping` is answered with an empty result; notifications are ignored.

## Error model

- Protocol errors use JSON-RPC error codes: `-32700` parse error, `-32600` invalid request, `-32601` method not found, `-32602` invalid params/unknown tool.
- Tool execution errors (e.g. ambiguous metric, missing data) return `isError: true` with the message in `content`, keeping protocol and business failures distinct.

## Privacy boundary

Tool results contain only derived signal, provenance, source counts, and retrieved document excerpts — never raw CSV rows. This matches the web workbench's evidence-snapshot boundary.

## Non-goals

- No resources, prompts, logging, or sampling capabilities; only `tools`.
- No HTTP/SSE transport; stdio only, matching how agents spawn subprocess tools.

## Acceptance

- `data2doc2data mcp` answers `initialize`, `tools/list`, and `tools/call` over stdio.
- `analyze` returns the same deterministic result as the CLI/web workbench.
- `source_profile` reports counts without raw values.
- The publish bundle includes `mcp_server.py`.
