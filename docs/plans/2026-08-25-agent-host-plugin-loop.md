# Agent Host Plugin Loop Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Deliver an end-to-end MCP business-analysis plugin with isolated task creation, local source detection, host-agent orchestration, real rule verification, bounded evidence, recovery, and truthful standalone reports.

**Architecture:** Extend the existing Python stdio MCP server with task-scoped orchestration tools backed by `WorkbenchService`, immutable snapshots, existing deterministic analysis engines, and the persisted evidence/run stores. Preserve legacy tools while routing complete plugin analysis through the same task/run/report pipeline as the web workbench; keep the external host as the only reasoning agent.

**Tech Stack:** Python 3.10+, stdlib JSON-RPC/SQLite/HTML parsing, existing NumPy/scikit-learn/jieba diagnostics, unittest/pytest, React/Vitest/TypeScript/Vite.

---

### Task 1: Lock failing host-plugin contract tests

**Files:**
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_integrations.py`
- Modify: `tests/test_reporting.py`
- Modify: `tests/test_source_resolver.py`

**Step 1:** Write failing tests for the new MCP tools and source-directory/embedded-report classification.

**Step 2:** Run `.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_reporting.py tests/test_source_resolver.py tests/test_integrations.py -q` and confirm failures arise from missing public contracts and disconnected report state.

**Step 3:** Add regression assertions for immutable task isolation, compact provenance, evaluated rule clauses, synchronized HTML report state, and automatic report delivery.

### Task 2: Build isolated source and task intake

**Files:**
- Modify: `src/data2doc2data/source_resolver.py`
- Modify: `src/data2doc2data/workspace_store.py`
- Create: `src/data2doc2data/plugin_service.py`
- Test: `tests/test_source_resolver.py`
- Test: `tests/test_mcp_server.py`

**Step 1:** Implement bounded directory expansion and mixed Markdown/HTML table extraction with honest unsupported-format diagnostics.

**Step 2:** Implement persistent task creation, immutable dataset/document snapshots, optional rules registration, and compact task-local source metadata.

**Step 3:** Re-run focused intake tests until they pass without writing to the legacy global profile.

### Task 3: Expose real host-orchestrated analysis and verification

**Files:**
- Modify: `src/data2doc2data/mcp_server.py`
- Modify: `src/data2doc2data/plugin_service.py`
- Modify: `src/data2doc2data/integrations.py`
- Test: `tests/test_mcp_server.py`
- Test: `tests/test_integrations.py`

**Step 1:** Expose source inspection, automatic task creation, task-local metric analysis, deterministic rule verdicts, observable traces, checkpoint resume, and one turnkey analysis tool.

**Step 2:** Route complete plugin execution through persisted workbench runs and redact absolute source paths/raw row-index arrays from host responses.

**Step 3:** Re-run focused host/plugin tests and prove both flagship cases remain isolated.

### Task 4: Unify truthful report state and full business findings

**Files:**
- Modify: `src/data2doc2data/reporting.py`
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `src/data2doc2data/mcp_server.py`
- Test: `tests/test_reporting.py`
- Test: `tests/test_mcp_server.py`

**Step 1:** Feed locked data dashboard, text dashboard, cycle artifacts, evidence graph, and actual run counts into cycle-based reports.

**Step 2:** Include verified metric findings and explicit rule/assumption verdicts in plugin-generated business reports.

**Step 3:** Assert completed reports never claim missing data/text/artifacts when corresponding persisted evidence exists.

### Task 5: Deliver installation, Skill, and host guidance

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `integrations/README.md`
- Modify: `integrations/codebuddy/README.md`
- Modify: `integrations/codex/README.md`
- Modify: `docs/plans/task.md`

**Step 1:** Document virtualenv-safe user-scope installation, natural-language setup, host approval boundaries, and concise real business prompts.

**Step 2:** Update all tool counts, task-scoped workflows, source support, privacy, report generation, and recovery semantics.

### Task 6: Final verification and product audit

**Files:**
- Modify: `docs/plans/task.md`

**Step 1:** Run `.venv/bin/python -m pytest -q`, `.venv/bin/python -m ruff check .`, `npm test -- --run`, `npm run typecheck`, and `npm run build` from the correct directories.

**Step 2:** Run `.venv/bin/data2doc2data doctor --json` and an actual JSON-RPC stdio integration exercise over both flagship cases, verifying task isolation, rule decisions, report hashes, and no path/raw-row leakage.

**Step 3:** Check Git status and preserve all pre-existing user files and private presentation ignore rules.
