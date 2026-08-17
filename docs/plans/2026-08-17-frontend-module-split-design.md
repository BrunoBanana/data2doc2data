# Frontend Module Split Design

**Date:** 2026-08-17

## Goal

Split the single 697-line `app.js` into focused ES modules without introducing a build step, so the evidence workbench stays maintainable as it grows.

## Decision

Use native ES modules served over the existing loopback HTTP server. The split follows the three-column information architecture plus shared cross-cutting concerns:

| Module | Responsibility |
|---|---|
| `state.js` | Mutable app state and display constants (labels, status maps). |
| `ui.js` | Side-effect-free presentation helpers (formatting, labels). |
| `api.js` | Loopback HTTP helpers (`request`, `agentRequest`). |
| `data-panel.js` | Source selection, demo scenarios, dataset profile. |
| `analysis-panel.js` | Deterministic analysis question and result rendering. |
| `assistant-panel.js` | Agent detection, session, event stream, approvals. |
| `app.js` | Entry point: workspace tabs and startup sequencing. |

- `index.html` loads `app.js` with `type="module"`; modules `import` sibling files by relative path with the `.js` extension.
- Cross-panel interactions go through explicit exports: `analysis-panel` exposes `invalidateAnalysisPresentation` and `setQuestion`; `assistant-panel` exposes `resetContextSummary` and `loadAgents`. State objects in `state.js` are shared by reference.

## Non-goals

- No bundler, transpiler, or minifier. Zero build step and zero new dependencies.
- No framework; modules are plain functions over the existing DOM.

## Why the contract tests changed

The security contracts (no `innerHTML`/`insertAdjacentHTML`/`eval`, no external origins, loopback-only routes) previously read only `app.js`. After the split they read a concatenation of every local `.js` module via a `read_all_js()` helper, so the safety boundary covers the whole frontend, not just the entry file.

## Acceptance

- Every module passes `node --check` in module mode.
- The server serves each module with `text/javascript` under the same static allowlist.
- The publish bundle includes every module (extended `PUBLIC_RESOURCE_FILES` and `EXPECTED_STATIC_FILES`).
- All security and feature contract tests pass against the concatenated modules.
