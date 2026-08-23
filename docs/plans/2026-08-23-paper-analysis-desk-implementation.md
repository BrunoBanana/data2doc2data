# Paper Analysis Desk Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Deliver the Paper Analysis Desk UI, two complete synthetic flagship cases, and verified Codex / DeepSeek Harness / WorkBuddy MCP integration packages on the existing local-first engine.

**Architecture:** Keep the Python deterministic analysis core, SQLite workbench store, and React task shell as the single runtime. Add a strict flagship-case package contract and one authenticated case-loading service that creates ordinary task snapshots, then restyle the existing workbench and report rather than building parallel screens. Agent hosts receive versioned configuration templates that all launch the existing stdio MCP server.

**Tech Stack:** Python 3.10+, stdlib HTTP/SQLite/MCP, React 19, TypeScript, Vite, Vitest, ECharts, XYFlow, Motion, Playwright.

---

### Task 1: Lock the selected visual target and visual baseline

**Files:**
- Create: `docs/design-references/2026-08-23/selected-evidence-blueprint.png`
- Create: `docs/design-references/2026-08-23/reference-desktop.png`
- Create: `docs/design-references/2026-08-23/reference-mobile.png`
- Create: `docs/design-references/2026-08-23/current-desktop.png`
- Create: `docs/design-references/2026-08-23/current-mobile.png`
- Modify: `docs/plans/task.md`

**Step 1: Record task 26 as in progress**

Append one table row describing the paper workbench, flagship cases, and agent-host integrations.

**Step 2: Verify the selected image dimensions**

Run: `file docs/design-references/2026-08-23/selected-evidence-blueprint.png`

Expected: a desktop landscape PNG (generated target is 1487 × 1058 and will be compared at a 1440 × 1024 browser viewport).

**Step 3: Commit**

```bash
git add docs/design-references docs/plans/task.md
git commit -m "docs: lock paper workbench visual target"
```

### Task 2: Define and validate complete flagship case packages

**Files:**
- Create: `src/data2doc2data/flagship_cases.py`
- Create: `tests/test_flagship_cases.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing contract tests**

```python
def test_catalog_exposes_exactly_two_complete_synthetic_cases():
    catalog = FlagshipCaseCatalog.load()
    assert [case.id for case in catalog.list()] == ["saas-growth-retention", "retail-promotion-fulfillment"]
    for case in catalog.list():
        package = catalog.package(case.id)
        assert package.record_count >= 200
        assert package.documents
        assert package.rules_path.is_file()
        assert package.hypotheses_path.is_file()
        assert package.expected_path.is_file()
        assert package.synthetic is True
```

Also test exact JSON fields, ID validation, containment, symlink rejection, duplicate `(date, metric, segment)` rejection, ISO dates, finite numeric values, referenced document existence, and golden-result references.

**Step 2: Run tests and confirm RED**

Run: `python -m unittest tests.test_flagship_cases -v`

Expected: FAIL because `data2doc2data.flagship_cases` does not exist.

**Step 3: Implement the strict catalog**

Create immutable `FlagshipCase`, `FlagshipCasePackage`, `FlagshipCaseCatalog`, and `FlagshipCaseError` types. Resolve every file below the package root and return only validated paths.

**Step 4: Run tests and confirm GREEN**

Run: `python -m unittest tests.test_flagship_cases -v`

Expected: all flagship-case contract tests pass.

**Step 5: Commit**

```bash
git add src/data2doc2data/flagship_cases.py tests/test_flagship_cases.py pyproject.toml
git commit -m "feat: define complete flagship case contract"
```

### Task 3: Add two rich deterministic case packs

**Files:**
- Create: `src/data2doc2data/sample/cases/catalog.json`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/case.json`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/metrics.csv`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/documents/*.md`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/rules.json`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/hypotheses.json`
- Create: `src/data2doc2data/sample/cases/saas-growth-retention/expected.json`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/case.json`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/metrics.csv`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/documents/*.md`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/rules.json`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/hypotheses.json`
- Create: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/expected.json`
- Modify: `tests/test_flagship_cases.py`

**Step 1: Add expected semantic assertions and confirm RED**

Assert 208 SaaS records across 26 weeks and 8 metrics with four Markdown documents; assert 260 retail records across 26 weeks and 10 metrics with five documents. Assert the intended inflection windows, rule IDs, hypotheses, and expected evidence statuses.

Run: `python -m unittest tests.test_flagship_cases -v`

Expected: FAIL because the packs are absent.

**Step 2: Add deterministic synthetic data and documents**

Use stable weekly values with explicit `synthetic: true` metadata. Make the data tell a non-trivial story: SaaS acquisition increases while activation/retention deteriorate; retail GMV increases while margin, delivery, returns, and repeat purchase deteriorate.

**Step 3: Confirm GREEN**

Run: `python -m unittest tests.test_flagship_cases tests.test_analysis tests.test_rules -v`

Expected: all tests pass.

**Step 4: Commit**

```bash
git add src/data2doc2data/sample/cases tests/test_flagship_cases.py
git commit -m "feat: add two complete synthetic analysis cases"
```

### Task 4: Expose one-click case loading through the workbench API

**Files:**
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_workbench_api.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/contracts/workbench.ts`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/features/onboarding/Onboarding.tsx`
- Modify: `web/src/features/onboarding/Onboarding.test.tsx`
- Modify: `web/src/app/App.test.tsx`

**Step 1: Write failing API and UI tests**

Test `GET /api/workbench/cases` returns safe metadata without local paths. Test `POST /api/workbench/cases/{id}/load` creates an owned task, registers one dataset and every document snapshot, persists case metadata, and can immediately build both dashboards. In React, test two visible case choices and a one-click load action.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_workbench_api.WorkbenchApiTest -v && cd web && npm test -- --run src/features/onboarding/Onboarding.test.tsx src/app/App.test.tsx`

Expected: FAIL because case endpoints and props do not exist.

**Step 3: Implement the smallest vertical slice**

Add:

```typescript
export interface FlagshipCaseSummary {
  id: string
  title: string
  summary: string
  business_question: string
  metric_count: number
  record_count: number
  document_count: number
  synthetic: true
}
```

The backend loader must reuse existing snapshot registration, document parsing, task ownership, and dashboard builders. It must never introduce a privileged bypass or expose package paths.

**Step 4: Confirm GREEN**

Run the focused Python and frontend commands from Step 2.

Expected: all focused tests pass.

**Step 5: Commit**

```bash
git add src/data2doc2data/workbench_api.py src/data2doc2data/server.py tests/test_workbench_api.py web/src
git commit -m "feat: load flagship cases into the workbench"
```

### Task 5: Rebuild the workbench as the selected evidence blueprint

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/features/tasks/TaskShell.tsx`
- Modify: `web/src/features/dashboard/DashboardCanvas.tsx`
- Modify: `web/src/features/evidence/EvidenceGraph.tsx`
- Modify: `web/src/features/evidence/EvidenceFlowCanvas.tsx`
- Modify: `web/src/features/runs/RunTimeline.tsx`
- Modify: `web/src/features/runs/RunPlayback.tsx`
- Modify: `web/src/features/assistant/AssistantDrawer.tsx`
- Modify: relevant `*.test.tsx` files beside these components

**Step 1: Write failing semantic UI tests**

Test the black local-status strip, `案例与资产` rail, dominant `证据链` canvas, `分析员笔记` margin, event-backed progress, semantic status labels, assistant collapse, mobile view switcher, and accessible reduced-motion behavior.

**Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/tasks src/features/dashboard src/features/evidence src/features/runs src/features/assistant`

Expected: new blueprint assertions fail.

**Step 3: Implement the Paper Analysis Desk design system**

Replace the dark glow tokens with paper/ink/grid tokens. Keep real controls and existing data bindings. Use CSS and the installed component/runtime libraries for interface layout and icons; do not add generated decorative assets or arbitrary model-generated code.

**Step 4: Implement observable process emphasis**

Make the evidence graph the primary evidence view; keep calculations, citations, hypotheses, verification status, approvals, and event ordering visible. Motion must derive from run-event state and stop under `prefers-reduced-motion`.

**Step 5: Confirm GREEN and build**

Run: `cd web && npm test -- --run && npm run typecheck && npm run build`

Expected: all frontend tests, typecheck, and build pass.

**Step 6: Commit**

```bash
git add web/src src/data2doc2data/static/dist
git commit -m "feat: build the paper evidence workbench"
```

### Task 6: Align standalone HTML reports with the paper workbench

**Files:**
- Modify: `src/data2doc2data/reporting.py`
- Modify: `tests/test_reporting.py`
- Modify: `web/src/features/reports/ReportExport.test.tsx`

**Step 1: Write failing report tests**

Assert paper tokens, print-safe styles, a decision summary, verification counts, source-backed findings, evidence citations, recommendations, and a strict offline CSP with no network assets.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_reporting -v`

Expected: paper-report assertions fail.

**Step 3: Implement and confirm GREEN**

Update the self-contained HTML and print CSS while preserving HTML escaping, CSP, bounded tables, and offline SVG chart rendering.

Run: `python -m unittest tests.test_reporting tests.test_workbench_api -v`

Expected: all report and API tests pass.

**Step 4: Commit**

```bash
git add src/data2doc2data/reporting.py tests/test_reporting.py web/src/features/reports/ReportExport.test.tsx
git commit -m "feat: export paper-native analysis reports"
```

### Task 7: Package Codex, DeepSeek Harness, and WorkBuddy integrations

**Files:**
- Create: `src/data2doc2data/integrations.py`
- Create: `integrations/codex/README.md`
- Create: `integrations/codex/config.toml.example`
- Create: `integrations/deepseek-harness/README.md`
- Create: `integrations/deepseek-harness/cordis.config.json.example`
- Create: `integrations/codebuddy/README.md`
- Create: `integrations/codebuddy/mcp.json.example`
- Modify: `src/data2doc2data/cli.py`
- Modify: `tests/test_cli.py`
- Create: `tests/test_integrations.py`
- Modify: `README.md`

**Step 1: Write failing doctor and manifest tests**

Test all templates parse, resolve to `data2doc2data mcp`, declare the same server name, and do not contain secrets or machine-specific absolute paths. Test `data2doc2data doctor --json` checks engine import, two case packs, MCP initialize/list/call, and emits actionable host configuration status without writing user files.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_cli tests.test_integrations -v`

Expected: FAIL because doctor and templates are absent.

**Step 3: Implement and confirm GREEN**

Use the existing MCP server and a subprocess-free in-process protocol probe where possible. Keep host-specific differences in configuration only.

Run: `python -m unittest tests.test_cli tests.test_integrations tests.test_mcp_server -v`

Expected: all integration and MCP contract tests pass.

**Step 4: Commit**

```bash
git add integrations src/data2doc2data/integrations.py src/data2doc2data/cli.py tests README.md
git commit -m "feat: package three agent host integrations"
```

### Task 8: Design QA, three use-test rounds, and release verification

**Files:**
- Create: `design-qa.md`
- Modify: `web/e2e/workbench.spec.ts`
- Create: `docs/testing/2026-08-23-paper-analysis-desk-use-tests.md`
- Modify: `docs/plans/task.md`
- Modify: release metadata/tests only if required by packaged files

**Step 1: Add failing end-to-end journeys**

Cover both flagship cases from onboarding to dashboard, analysis run, evidence graph, assistant collapse, and HTML download. Add desktop 1440 × 1024, mobile 390 × 844, reduced-motion, zero horizontal overflow, and zero console-error assertions.

**Step 2: Run and confirm RED, then fix**

Run: `cd web && npm run e2e`

Expected: new journeys fail before final selectors/states are implemented, then pass after fixes.

**Step 3: Run blocking visual QA**

Capture the selected reference and current implementation in the same 1440 × 1024 state. Compare hierarchy, spacing, colors, typography, evidence graph emphasis, assistant margin, responsive behavior, and interactions. Save findings in `design-qa.md`; fix P0/P1/P2 issues and repeat until it contains `final result: passed`.

**Step 4: Run three real-use rounds**

1. SaaS case: identify acquisition/retention divergence and verify citations.
2. Retail case: identify promotion/margin/fulfillment conflicts and verify evidence graph plus report.
3. Agent-host case: run MCP initialize, list tools, source profile, analyze, and rules validation through each manifest contract.

Document each observed issue, fix, and rerun in `docs/testing/2026-08-23-paper-analysis-desk-use-tests.md`.

**Step 5: Run the complete fresh verification suite**

```bash
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python -m ruff check .
cd web && npm test -- --run && npm run typecheck && npm run build && npm audit --audit-level=high && npm run e2e
```

Expected: zero failures, coverage above the configured threshold, Ruff clean, frontend tests/typecheck/build/audit clean, and Playwright journeys pass (with explicitly gated live-host tests skipped only when the host is unavailable).

**Step 6: Complete the tracker and commit**

```bash
git add design-qa.md docs web/e2e src/data2doc2data/static/dist
git commit -m "test: verify paper analysis desk delivery"
```
