# Business Analysis Task Workbench Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Rebuild data2doc2data as a task-first local business-analysis workbench where users connect an assistant, import data and optional documents, receive combined dashboards, and inspect every calculation, retrieval, evidence link, hypothesis, and approval.

**Architecture:** Keep the secure Python loopback host as the authority for files, queries, approvals, snapshots, and agent sessions. Add versioned task/run/dashboard/evidence contracts and SQLite-backed metadata, then replace the legacy page with a React + TypeScript + Vite application. The agent proposes bounded declarative plans; the host validates and executes them locally; the browser renders Flint chart specifications and React Flow evidence graphs without executing agent-authored code.

**Tech Stack:** Python 3.10+ stdlib and unittest, SQLite, React 19, TypeScript, Vite, Vitest, Testing Library, Playwright, Microsoft Flint, Apache ECharts, React Flow/xyflow, CSS, Ruff.

---

### Task 1: Introduce the versioned task and run domain

**Files:**
- Create: `src/data2doc2data/workspace.py`
- Create: `src/data2doc2data/run_events.py`
- Create: `tests/test_workspace.py`
- Create: `tests/test_run_events.py`

**Steps:**
1. Write failing tests for `AnalysisTask`, `AnalysisRun`, immutable snapshot references, allowed status transitions, event sequence validation, safe summaries, and versioned JSON round-trips.
2. Run `python -m unittest tests.test_workspace tests.test_run_events -v`; expect import failures.
3. Implement dataclass-based contracts with UTC timestamps, stable identifiers, strict enum validation, monotonic run-event sequences, and no raw record payloads in event summaries.
4. Re-run the focused tests; expect all to pass.
5. Run `ruff check src/data2doc2data/workspace.py src/data2doc2data/run_events.py tests/test_workspace.py tests/test_run_events.py`.
6. Commit with `git commit -m "feat: add task and run event contracts"`.

### Task 2: Add the local SQLite metadata store

**Files:**
- Create: `src/data2doc2data/workspace_store.py`
- Create: `tests/test_workspace_store.py`
- Modify: `src/data2doc2data/config.py`

**Steps:**
1. Write failing tests for schema creation, task/run CRUD, immutable snapshot references, ordered event replay, transactional writes, corrupt-database errors, restrictive file permissions, and JSON-state migration compatibility.
2. Run `python -m unittest tests.test_workspace_store -v`; expect import failures.
3. Implement a stdlib `sqlite3` store with explicit schema versioning, foreign keys, WAL mode, parameterized SQL, atomic transactions, and owner-only database permissions.
4. Re-run the focused tests; expect all to pass.
5. Run the existing config and session suites to confirm no profile regression.
6. Commit with `git commit -m "feat: persist analysis tasks and runs"`.

### Task 3: Expose task, asset, and run APIs

**Files:**
- Create: `src/data2doc2data/workbench_api.py`
- Create: `tests/test_workbench_api.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_server.py`

**Steps:**
1. Write failing HTTP tests for listing/creating/updating tasks, attaching existing data and document snapshots, starting a run, replaying events after a sequence number, ownership isolation, invalid identifiers, CSRF enforcement, and bounded response sizes.
2. Run `python -m unittest tests.test_workbench_api tests.test_server -v`; expect the new routes to return 404.
3. Implement `/api/workbench/tasks`, `/api/workbench/tasks/{id}`, `/api/workbench/tasks/{id}/assets`, `/api/workbench/tasks/{id}/runs`, and `/api/workbench/runs/{id}/events` using the existing cookie/CSRF boundary.
4. Re-run the focused tests; expect all to pass.
5. Run `python -m unittest tests.test_agent_server tests.test_server_ingestion tests.test_server_ingestion_http -v` for gateway and ingestion regressions.
6. Commit with `git commit -m "feat: expose workbench task APIs"`.

### Task 4: Build deterministic data profiling and dashboard contracts

**Files:**
- Create: `src/data2doc2data/dashboard.py`
- Create: `src/data2doc2data/data_profile.py`
- Create: `tests/test_dashboard.py`
- Create: `tests/test_data_profile.py`

**Steps:**
1. Write failing tests for `DashboardSpec`, KPI/card/table/chart blocks, supported Flint marks and transforms, query provenance, row/result limits, unsafe expression rejection, empty datasets, quality metrics, time coverage, numeric distributions, category Top-N, and stable JSON output.
2. Run `python -m unittest tests.test_dashboard tests.test_data_profile -v`; expect import failures.
3. Implement a declarative, versioned dashboard contract and a model-free profiler that reads existing immutable ingestion snapshots and produces bounded aggregate artifacts only.
4. Re-run the focused tests; expect all to pass.
5. Run `python -m unittest tests.test_analysis tests.test_ingestion tests.test_metrics tests.test_quality_contract -v`.
6. Commit with `git commit -m "feat: add deterministic dashboard planning"`.

### Task 5: Add document corpus and text-dashboard contracts

**Files:**
- Create: `src/data2doc2data/documents.py`
- Create: `src/data2doc2data/text_dashboard.py`
- Create: `tests/test_documents.py`
- Create: `tests/test_text_dashboard.py`

**Steps:**
1. Write failing tests for Markdown/TXT parsing, section and line provenance, normalized hashes, duplicate detection, partial corpus failure, bounded topic/entity summaries, claim states, conflict links, and exact source citations.
2. Run `python -m unittest tests.test_documents tests.test_text_dashboard -v`; expect import failures.
3. Implement adapters over the existing retrieval/provenance modules; never convert an extracted claim directly into a deterministic conclusion.
4. Re-run the focused tests; expect all to pass.
5. Run `python -m unittest tests.test_retrieval tests.test_provenance tests.test_evidence_context -v`.
6. Commit with `git commit -m "feat: add text dashboard pipeline"`.

### Task 6: Build the local analysis orchestrator and evidence graph

**Files:**
- Create: `src/data2doc2data/orchestrator.py`
- Create: `src/data2doc2data/evidence_graph.py`
- Create: `tests/test_orchestrator.py`
- Create: `tests/test_evidence_graph.py`

**Steps:**
1. Write failing tests for model-free runs, model-enhanced proposals, event ordering, resumable failure, calculation/retrieval/chart/claim/hypothesis/validation events, evidence node types, allowed edge relations, contradiction handling, insufficient-evidence states, and source snapshot pinning.
2. Run `python -m unittest tests.test_orchestrator tests.test_evidence_graph -v`; expect import failures.
3. Implement the host-owned state machine. Reuse existing analysis, hypotheses, retrieval, agent gateway, and approval services; accept only structured bounded proposals from an agent.
4. Re-run the focused tests; expect all to pass.
5. Run the full Python test suite once to catch contract incompatibilities.
6. Commit with `git commit -m "feat: orchestrate observable analysis runs"`.

### Task 7: Add provider connection status and onboarding APIs

**Files:**
- Create: `src/data2doc2data/providers.py`
- Create: `tests/test_providers.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_agent_server.py`

**Steps:**
1. Write failing tests for Codex CLI, WorkBuddy/CodeBuddy CLI, OpenAI-compatible API references, skip mode, health checks, expired authorization, redacted settings, environment/keychain references, and reconnect hints.
2. Run `python -m unittest tests.test_providers tests.test_agent_server -v`; expect the registry tests to fail.
3. Implement the registry on top of the current adapters without persisting raw secrets; expose status and capability metadata to the onboarding page.
4. Re-run the focused provider, Codex, and WorkBuddy suites.
5. Commit with `git commit -m "feat: unify assistant provider connections"`.

### Task 8: Scaffold the React workbench and production asset build

**Files:**
- Create: `web/package.json`
- Create: `web/package-lock.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/src/main.tsx`
- Create: `web/src/app/App.tsx`
- Create: `web/src/app/App.test.tsx`
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/app.css`
- Modify: `src/data2doc2data/server.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_static_assets.py`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `tests/test_release_bundle.py`

**Steps:**
1. Add failing Python contracts for safe recursive serving of hashed `static/dist` files, SPA fallback, MIME types, traversal rejection, package data, and release-bundle inclusion.
2. Add a failing Vitest smoke test for the application shell and no-provider fallback.
3. Run the focused Python tests and `npm test -- --run` from `web`; expect missing-build failures.
4. Add the locked React/Vite/Vitest toolchain and implement the smallest task shell. Configure Vite to emit into `src/data2doc2data/static/dist` with no CDN dependency.
5. Implement contained static serving and update packaging/bundle allowlists without weakening the current host or CSP controls.
6. Run `npm run typecheck`, `npm test -- --run`, `npm run build`, and the focused Python suites.
7. Commit with `git commit -m "feat: scaffold react analysis workbench"`.

### Task 9: Implement onboarding, task home, and data import journey

**Files:**
- Create: `web/src/api/client.ts`
- Create: `web/src/features/onboarding/Onboarding.tsx`
- Create: `web/src/features/tasks/TaskHome.tsx`
- Create: `web/src/features/tasks/TaskShell.tsx`
- Create: `web/src/features/assets/DataImport.tsx`
- Create: `web/src/features/onboarding/Onboarding.test.tsx`
- Create: `web/src/features/tasks/TaskHome.test.tsx`
- Create: `web/src/features/assets/DataImport.test.tsx`

**Steps:**
1. Write failing component tests for connect/skip, reconnect errors, task templates, task creation, CSV/local-path/API ingestion, preview/mapping, explicit approval, progress recovery, keyboard navigation, and 390px layout.
2. Run the three focused Vitest files; expect failures.
3. Implement the guided first-run flow and task home using the existing ingestion APIs plus the new task/provider APIs.
4. Re-run the focused tests and typecheck.
5. Run `npm run build` and the existing ingestion web-contract suites.
6. Commit with `git commit -m "feat: build task-first onboarding flow"`.

### Task 10: Implement the combined data and text dashboard

**Files:**
- Create: `web/src/contracts/dashboard.ts`
- Create: `web/src/features/dashboard/DashboardCanvas.tsx`
- Create: `web/src/features/dashboard/ChartCard.tsx`
- Create: `web/src/features/dashboard/DataProfilePanel.tsx`
- Create: `web/src/features/documents/DocumentImport.tsx`
- Create: `web/src/features/documents/TextDashboard.tsx`
- Create: `web/src/features/dashboard/DashboardCanvas.test.tsx`
- Create: `web/src/features/documents/TextDashboard.test.tsx`

**Steps:**
1. Write failing tests for KPI/chart/table rendering, Flint-spec validation, ECharts option compilation, provenance drawers, loading/error/empty states, document partial success, topic/entity/timeline/claim views, and data-supported/contradicted/pending status labels.
2. Run the focused Vitest files; expect failures.
3. Implement the dashboard renderer and text dashboard. Keep all raw values as text nodes, reject unknown chart operators, and lazy-load chart code.
4. Re-run tests, typecheck, and production build.
5. Add a model-free golden DashboardSpec and assert it renders from the bundled synthetic scenario.
6. Commit with `git commit -m "feat: deliver combined analysis dashboards"`.

### Task 11: Visualize run timelines, evidence chains, and hypotheses

**Files:**
- Create: `web/src/contracts/run-events.ts`
- Create: `web/src/features/runs/RunTimeline.tsx`
- Create: `web/src/features/evidence/EvidenceGraph.tsx`
- Create: `web/src/features/evidence/HypothesisPanel.tsx`
- Create: `web/src/features/runs/RunTimeline.test.tsx`
- Create: `web/src/features/evidence/EvidenceGraph.test.tsx`
- Modify: `web/src/styles/app.css`

**Steps:**
1. Write failing tests for ordered SSE replay, disconnect resume, running/completed/failed steps, formulas and queries, document snippets, graph filters, node expansion, support/contradiction/insufficient edges, no hidden chain-of-thought field, and reduced-motion behavior.
2. Run the focused Vitest files; expect failures.
3. Implement the bottom run drawer and React Flow graph using stable backend event contracts. Animate only event-backed state changes and stop continuous motion when reduced motion is requested.
4. Re-run tests, typecheck, and build.
5. Commit with `git commit -m "feat: visualize evidence and hypothesis runs"`.

### Task 12: Move Codex and WorkBuddy into the assistant drawer

**Files:**
- Create: `web/src/features/assistant/AssistantDrawer.tsx`
- Create: `web/src/features/assistant/ApprovalCard.tsx`
- Create: `web/src/features/assistant/AssistantDrawer.test.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `tests/test_web_agent_contract.py`

**Steps:**
1. Write failing tests for the collapsed 340px drawer, task-aware bounded context, provider switching, streaming aggregation, interrupt, approval pinning, Markdown safety, authorization recovery, and keeping the dashboard as the visual center.
2. Run the focused Vitest and Python web-contract tests; expect failures.
3. Port the current assistant behavior into typed React components while preserving provider-neutral session APIs and all approval/security guarantees.
4. Re-run focused tests, Node/type checks, and the Codex/WorkBuddy adapter suites.
5. Commit with `git commit -m "feat: integrate assistant analysis drawer"`.

### Task 13: Add task history, replay, and resilient error recovery

**Files:**
- Create: `web/src/features/history/RunHistory.tsx`
- Create: `web/src/features/history/RunHistory.test.tsx`
- Modify: `src/data2doc2data/orchestrator.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `web/src/app/App.tsx`

**Steps:**
1. Write failing tests for recent tasks, failed-run diagnosis, event replay, retry from a safe step, stale snapshot warnings, model-unavailable deterministic fallback, document partial failure, and preserving user-entered connection/import configuration.
2. Run the focused Python and Vitest suites; expect failures.
3. Implement run history and recovery actions with idempotency tokens and immutable prior runs.
4. Re-run focused tests, typecheck, and build.
5. Commit with `git commit -m "feat: add analysis history and recovery"`.

### Task 14: Add event-backed playback and synchronized evidence motion

**Files:**
- Create: `web/src/features/runs/RunPlayback.tsx`
- Create: `web/src/features/runs/RunPlayback.test.tsx`
- Modify: `web/src/features/runs/RunTimeline.tsx`
- Modify: `web/src/features/evidence/EvidenceGraph.tsx`
- Modify: `web/src/features/evidence/EvidenceFlowCanvas.tsx`
- Modify: `web/src/styles/app.css`

**Steps:**
1. Write failing tests for play/pause/seek/speed/skip, progressive event reveal, synchronized graph-node highlighting, terminal and failed states, truthful replay labeling, keyboard controls, and reduced-motion instant transitions.
2. Add the locked Motion dependency only for event-backed layout/state transitions; keep React Flow as the graph renderer and avoid displaying hidden chain-of-thought.
3. Implement a replay controller that progressively reveals persisted events and highlights their artifact references in the evidence graph and hypothesis panel.
4. Re-run focused tests, typecheck, production build, and a browser performance pass with large bounded graphs.
5. Commit with `git commit -m "feat: animate observable analysis playback"`.

### Task 15: Generate executive reports and downloadable standalone HTML

**Files:**
- Create: `src/data2doc2data/reporting.py`
- Create: `tests/test_reporting.py`
- Create: `web/src/features/reports/ReportExport.tsx`
- Create: `web/src/features/reports/ReportExport.test.tsx`
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/features/tasks/TaskShell.tsx`

**Steps:**
1. Write failing tests for answer-first executive structure, KPI and text findings, inline SVG visual evidence, evidence/hypothesis provenance, next steps, further questions, caveats, locked snapshot identifiers, HTML escaping, no raw rows/paths/secrets, no external resources, print styles, and attachment headers.
2. Implement a host-generated, self-contained semantic HTML artifact with inline CSS/SVG and progressive `<details>` evidence; do not depend on a CDN or execute agent-authored markup.
3. Add an authenticated task report endpoint and browser download control that names the file safely and works offline after download.
4. Validate the report in desktop/mobile browsers, print preview, HTML validators, and a no-network browser context.
5. Commit with `git commit -m "feat: export standalone analysis reports"`.

### Task 16: Complete accessibility, security, and public release boundaries

**Files:**
- Create: `web/e2e/workbench.spec.ts`
- Create: `web/playwright.config.ts`
- Modify: `tests/test_public_boundary.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_static_assets.py`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Steps:**
1. Add failing checks for CSP-compatible production output, no source maps/private state in bundles, offline assets, keyboard-only task completion, focus trapping/restoration, WCAG AA color contrast, reduced motion, no horizontal overflow at 390px, and unsupported-browser messaging.
2. Run the focused release/security suites and Playwright test; expect failures.
3. Fix remaining release, accessibility, and security gaps; document connection modes, local-data boundaries, agent-visible context, and the observable-process model.
4. Run `npm audit --omit=dev`, `npm run typecheck`, `npm test -- --run`, `npm run build`, `ruff check .`, the complete Python suite, and coverage with the existing 80% floor.
5. Build the deterministic public ZIP twice and confirm identical SHA-256 hashes.
6. Commit with `git commit -m "chore: harden workbench release"`.

### Task 17: Run three end-to-end use-test and optimization rounds

**Files:**
- Create: `docs/testing/2026-08-23-business-analysis-workbench-use-tests.md`
- Modify: `docs/plans/task.md`
- Modify: `CHANGELOG.md`
- Modify: implementation and test files discovered by each round

**Steps:**
1. **Round 1 — model-free analyst:** create a task, import the bundled synthetic data, inspect profile/quality/dashboard, add bundled documents, and verify every visible fact links to a local snapshot. Record friction and fix it with a failing regression test first.
2. **Round 2 — local assistant analyst:** connect Codex, then WorkBuddy if available; ask for an anomaly investigation; verify bounded context, calculations, retrievals, approvals, evidence links, hypotheses, contradiction handling, interrupt, and authorization recovery. Fix each material issue with a failing test first.
3. **Round 3 — resilience and responsive use:** exercise API ingestion, a malformed document, SSE disconnect/replay, model outage fallback, keyboard-only desktop use, 1280px layout, 390px layout, reduced motion, and browser console/network errors. Fix each material issue with a failing test first.
4. Run all frontend and backend quality gates twice after the final fix.
5. Record exact commands, counts, coverage, browser sizes, provider versions, known limitations, and deterministic bundle SHA-256 in the use-test report and task tracker.
6. Commit with `git commit -m "test: verify business analysis workbench"`.
