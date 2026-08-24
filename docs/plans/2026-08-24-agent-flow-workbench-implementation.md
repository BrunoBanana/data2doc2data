# Agent Flow Workbench Redesign Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Rebuild Data2Doc2Data around a dual-runner Agent Flow that performs local data-text cross-reasoning, streams a live evidence canvas, survives browser/CLI disconnects, and generates the same offline HTML report from Web, CLI, and MCP.

**Architecture:** Extend the existing immutable `RunEvent`, SQLite `WorkspaceStore`, deterministic orchestrator, agent gateway, and React/XYFlow workbench instead of introducing a second runtime. A `DemoFlowRunner` and a connected `AgentFlowRunner` emit one cursor-based event contract into the existing run store; local tools own parsing and computation, while agents only create validated plans and invoke bounded tools. The UI projects those events into a dynamic graph, and reports/knowledge artifacts consume the same persisted run.

**Tech Stack:** Python 3.10+, stdlib HTTP/SQLite/SSE, optional MarkItDown/Docling adapters, React 19, TypeScript, Vite, Vitest, XYFlow, ECharts, Playwright, MCP JSON-RPC.

---

### Task 1: Expand the typed Flow event contract

**Files:**
- Modify: `src/data2doc2data/run_events.py`
- Modify: `web/src/contracts/run-events.ts`
- Test: `tests/test_run_events.py`
- Test: `web/src/features/runs/RunPlayback.test.tsx`

**Step 1: Write failing event-contract tests**

Add tests proving that plan revisions, tool progress, graph mutations, conflicts, report artifacts, and knowledge candidates are accepted, while private reasoning and raw rows remain rejected.

```python
def test_flow_events_cover_live_graph_and_tool_lifecycle():
    kinds = (
        "plan.created", "plan.revised", "step.added", "tool.started",
        "tool.progress", "tool.result", "node.added", "node.updated",
        "edge.added", "edge.activated", "conflict.detected",
        "knowledge.candidate", "report.generated",
    )
    for sequence, kind in enumerate(kinds, 1):
        assert RunEvent.create("run-live", sequence, kind, "flow", {"node_id": "node-1"}).kind == kind
```

**Step 2: Verify RED**

Run: `python -m unittest tests.test_run_events -v`

Expected: new event kinds fail as unknown.

**Step 3: Implement the event vocabulary and public TypeScript union**

Keep summaries JSON-safe, bounded to 4 KiB, append-only, and free of `raw_rows`, `chain_of_thought`, prompts, secrets, and local paths.

**Step 4: Confirm GREEN and commit**

Run: `python -m unittest tests.test_run_events -v && cd web && npm test -- --run src/features/runs/RunPlayback.test.tsx`

Commit: `feat: define live agent flow events`

### Task 2: Build bounded local data-text tools and input resolution

**Files:**
- Create: `src/data2doc2data/flow_tools.py`
- Create: `src/data2doc2data/source_resolver.py`
- Test: `tests/test_flow_tools.py`
- Test: `tests/test_source_resolver.py`
- Modify: `pyproject.toml`

**Step 1: Write failing tests for mixed inputs**

Cover CSV, Markdown with an embedded table, a text-only document, a data-plus-document pair, unsupported binary input, optional converter absence, size limits, symlink containment, and partial extraction diagnostics.

```python
def test_markdown_report_yields_text_and_embedded_dataset(tmp_path):
    source = tmp_path / "review.md"
    source.write_text("# 复盘\n转化下降。\n\n| date | metric | value |\n|---|---|---|\n| 2026-01-01 | conversion | 0.2 |", encoding="utf-8")
    resolved = SourceResolver().resolve((source,))
    assert resolved.modalities == ("data", "text")
    assert resolved.datasets[0].row_count == 1
    assert resolved.documents[0].sections
```

**Step 2: Verify RED**

Run: `python -m unittest tests.test_source_resolver tests.test_flow_tools -v`

**Step 3: Implement minimal adapters**

Implement `inspect_sources`, Markdown table extraction, existing CSV/document adapters, `profile_data`, `query_data`, `extract_claims`, `align_evidence`, `test_hypothesis`, and a typed `ToolResult`. Add an optional `markitdown` adapter discovered at runtime; report an actionable capability message when PDF/DOCX/XLSX conversion is unavailable. Do not make Docling or a model download a mandatory install.

**Step 4: Confirm GREEN and commit**

Run: `python -m unittest tests.test_source_resolver tests.test_flow_tools tests.test_documents tests.test_data_profile -v`

Commit: `feat: add local cross-reasoning tools`

### Task 3: Replace replay-only orchestration with dual Flow runners

**Files:**
- Create: `src/data2doc2data/flow_engine.py`
- Modify: `src/data2doc2data/orchestrator.py`
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `src/data2doc2data/workspace_store.py`
- Test: `tests/test_flow_engine.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_workbench_api.py`

**Step 1: Write failing Demo Runner tests**

Assert that the run begins with only `run.started`, persists events incrementally, adds graph nodes and edges as tools complete, contains at least one branch/conflict in each flagship case, and creates the report only after evidence convergence.

```python
def test_demo_runner_builds_the_graph_incrementally(store, flagship_task):
    observed = []
    result = DemoFlowRunner(store).run(flagship_task, on_event=observed.append)
    assert observed[0].kind == "run.started"
    assert any(event.kind == "node.added" for event in observed)
    assert any(event.kind == "edge.activated" for event in observed)
    assert any(event.kind in {"conflict.detected", "plan.revised"} for event in observed)
    assert observed[-1].kind == "run.completed"
```

**Step 2: Verify RED**

Run: `python -m unittest tests.test_flow_engine -v`

**Step 3: Implement `AgentFlowEngine` and `DemoFlowRunner`**

Use explicit limits: 32 steps, 3 plan revisions, 4 KiB event summaries, 1,000-row tool result caps, cancellation checks between steps, and stable artifact references. Save a graph projection after each mutation so reconnecting clients can catch up without reconstructing private state.

**Step 4: Add connected runner plan validation**

Accept only a structured plan of registered tool names, stable step IDs, dependencies, purpose, and bounded arguments. Reject cycles unless declared as a revision edge and reject arbitrary shell/code execution.

**Step 5: Confirm GREEN and commit**

Run: `python -m unittest tests.test_flow_engine tests.test_orchestrator tests.test_workbench_api -v`

Commit: `feat: execute dual-runner agent flows`

### Task 4: Stream live run events and support cursor reattachment

**Files:**
- Modify: `src/data2doc2data/server.py`
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/app/App.tsx`
- Test: `tests/test_workbench_api.py`
- Test: `tests/test_server.py`
- Test: `web/src/api/client.test.ts`

**Step 1: Write failing streaming tests**

Cover an asynchronous run returning `202`, an SSE endpoint with `id:` cursors and keepalives, replay after cursor, deduplication, completion, cancellation, and reattachment after page refresh.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_server tests.test_workbench_api -v && cd web && npm test -- --run src/api/client.test.ts`

**Step 3: Implement asynchronous execution and client stream**

`POST /runs` creates and starts the run without waiting for all computation. `GET /runs/{id}/stream?after=N` replays persisted events, then follows new events. The React client stores the last applied cursor per run and ignores duplicates.

**Step 4: Confirm GREEN and commit**

Commit: `feat: stream resumable workbench runs`

### Task 5: Make browser and CLI agent sessions durable

**Files:**
- Modify: `src/data2doc2data/agent_api.py`
- Modify: `src/data2doc2data/agents/workbuddy.py`
- Modify: `src/data2doc2data/agents/codex.py`
- Modify: `src/data2doc2data/sessions.py`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/features/assistant/AssistantDrawer.tsx`
- Test: `tests/test_agent_server.py`
- Test: `tests/test_workbuddy_adapter.py`
- Test: `tests/test_codex_adapter.py`
- Test: `web/src/features/assistant/AssistantDrawer.test.tsx`

**Step 1: Write failing expiry and reconnect tests**

Use a short fake lease to prove that renewing a browser session preserves owner identity and rotates CSRF safely. Simulate WorkBuddy SSE closure, health recovery, exponential reconnect, provider-session resume, event replay, and authentication-required terminal state.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_agent_server tests.test_workbuddy_adapter tests.test_codex_adapter -v`

**Step 3: Implement stable ownership and sliding renewal**

Separate stable owner identity from rotating CSRF lease. Refresh on authenticated activity and a bounded client heartbeat. Persist resumable provider IDs without storing bearer tokens.

**Step 4: Implement connection supervision**

Clear stale connection IDs when the SSE worker dies, reconnect with capped jittered backoff, run a health probe, rebuild ACP transport, resume active sessions, and surface `reconnecting`, `connected`, `auth_required`, or `failed` to the UI.

**Step 5: Confirm GREEN and commit**

Commit: `fix: keep local agent sessions attached`

### Task 6: Add project-scoped knowledge evolution

**Files:**
- Create: `src/data2doc2data/knowledge.py`
- Modify: `src/data2doc2data/workspace_store.py`
- Modify: `src/data2doc2data/flow_engine.py`
- Test: `tests/test_knowledge.py`
- Test: `tests/test_workspace_store.py`

**Step 1: Write failing versioning tests**

Cover project isolation, candidate creation, deterministic verification, explicit approval, superseding, rejection, provenance, validity intervals, and retrieval that excludes unverified candidates from facts.

**Step 2: Verify RED**

Run: `python -m unittest tests.test_knowledge tests.test_workspace_store -v`

**Step 3: Implement append-only knowledge records**

Add `candidate`, `verified`, `superseded`, and `rejected` states. Store source refs, run ID, evidence refs, `valid_from`, `valid_to`, and replacement ID. Never silently promote model-only output.

**Step 4: Confirm GREEN and commit**

Commit: `feat: add governed project knowledge evolution`

### Task 7: Fix Web report downloads and expose report generation to CLI/MCP

**Files:**
- Modify: `web/src/features/reports/ReportExport.tsx`
- Modify: `web/src/features/reports/ReportExport.test.tsx`
- Modify: `src/data2doc2data/reporting.py`
- Modify: `src/data2doc2data/cli.py`
- Modify: `src/data2doc2data/mcp_server.py`
- Modify: `src/data2doc2data/integrations.py`
- Test: `tests/test_reporting.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_mcp_server.py`
- Test: `web/e2e/workbench.spec.ts`

**Step 1: Write failing download test**

The component test must observe an appended anchor and delayed URL revocation. Playwright must wait for a real `.html` download, read it, and assert the title, conclusion, citations, Flow summary, CSP, and absence of network references.

**Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/reports/ReportExport.test.tsx && npm run e2e -- e2e/workbench.spec.ts`

**Step 3: Fix browser download lifecycle**

Append the anchor, trigger it, remove it, and revoke the Blob URL on a later task. Only display success after the click path completes.

**Step 4: Add CLI and MCP tools**

Add `data2doc2data report --task ID --output FILE` and MCP `generate_html_report`. Return JSON text plus a resource link containing MIME type, bounded filename, SHA-256, and artifact URI/path below the approved output root.

**Step 5: Confirm GREEN and commit**

Run: `python -m unittest tests.test_reporting tests.test_cli tests.test_mcp_server tests.test_integrations -v`

Commit: `feat: generate reports from web cli and mcp`

### Task 8: Correct the full-viewport workbench and fixed Agent Console

**Files:**
- Modify: `web/src/features/tasks/TaskShell.tsx`
- Modify: `web/src/features/assistant/AssistantDrawer.tsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/styles/tokens.css`
- Test: `web/src/features/assistant/AssistantDrawer.test.tsx`
- Test: `web/src/app/App.test.tsx`
- Test: `web/e2e/workbench.spec.ts`

**Step 1: Write failing layout tests**

Assert a full-height shell, independently scrollable asset rail, fixed-height central workspace, fixed assistant header/composer, scrollable conversation, visible composer at 1440×1024 without page scrolling, and mobile Agent panel behavior.

**Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/assistant/AssistantDrawer.test.tsx src/app/App.test.tsx`

**Step 3: Implement the selected Evidence Blueprint layout**

Use `height: 100dvh`, `min-height: 0`, and explicit overflow ownership at every grid/flex boundary. Keep the composer in normal flex layout at the bottom of the fixed drawer rather than using a document-level fixed overlay.

**Step 4: Confirm GREEN and commit**

Commit: `fix: keep the agent console in the workbench viewport`

### Task 9: Replace card playback with a live XYFlow execution canvas

**Files:**
- Create: `web/src/features/flow/AgentFlowCanvas.tsx`
- Create: `web/src/features/flow/FlowNode.tsx`
- Create: `web/src/features/flow/FlowInspector.tsx`
- Create: `web/src/features/flow/flow-projection.ts`
- Create: `web/src/features/flow/flow-projection.test.ts`
- Modify: `web/src/features/tasks/TaskShell.tsx`
- Modify: `web/src/features/evidence/EvidenceFlowCanvas.tsx`
- Modify: `web/src/styles/app.css`
- Test: `web/e2e/workbench.spec.ts`

**Step 1: Write failing projection tests**

Feed events one by one and assert that the projection starts empty, adds nodes only on `node.added`, grows edges on `edge.added`, activates a tool node during progress, retains superseded branches, displays conflict loops, and converges at report generation.

**Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/flow/flow-projection.test.ts`

**Step 3: Implement event-to-graph projection**

Use stable node IDs, five semantic lanes, animated active edges, auto-layout after node measurement, preserved manual viewport, details inspector, minimap/controls, and no raw row rendering. Under reduced motion, disable travel animations while retaining state transitions.

**Step 4: Make Flow the default analysis surface**

During a run, show the live canvas immediately. KPI cards update as artifacts arrive. The bottom step bar navigates to nodes but does not replace the canvas.

**Step 5: Confirm GREEN and commit**

Run: `cd web && npm test -- --run && npm run typecheck && npm run build`

Commit: `feat: visualize live agent flow construction`

### Task 10: Separate Demo and connected analysis journeys

**Files:**
- Modify: `web/src/features/onboarding/Onboarding.tsx`
- Modify: `web/src/features/onboarding/Onboarding.test.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `src/data2doc2data/flagship_cases.py`
- Modify: `src/data2doc2data/workbench_api.py`
- Test: `tests/test_flagship_cases.py`
- Test: `tests/test_workbench_api.py`
- Test: `web/e2e/workbench.spec.ts`

**Step 1: Write failing journey tests**

Test two primary entry cards: `立即体验 Demo` works with every agent unavailable; `连接 Agent 开始分析` requires a selected provider but can use either bundled materials or user files. Confirm that loading materials does not auto-inject expected answers into the connected runner.

**Step 2: Verify RED**

Run focused Python, Vitest, and Playwright tests.

**Step 3: Implement the two journeys**

Keep the two case packs as reusable material packages. Add a versioned demo flow manifest separately from hypotheses/expected test files. Label every Demo result as deterministic and synthetic.

**Step 4: Confirm GREEN and commit**

Commit: `feat: separate demo and connected analysis modes`

### Task 11: Three use rounds, visual QA, and release verification

**Files:**
- Modify: `design-qa.md`
- Create: `docs/testing/2026-08-24-agent-flow-use-tests.md`
- Modify: `docs/plans/task.md`
- Modify: release tests and metadata if packaged files change

**Step 1: Round 1 — no-model Demo**

Run both cases from the Demo entry. Verify the empty-to-complete canvas, real tool events, conflict branch, fixed Agent Console, report download, and reduced motion. Fix all P0/P1 findings and rerun.

**Step 2: Round 2 — connected Agent and mixed document**

Use real WorkBuddy and Codex when available. Analyze one Markdown report containing text plus a table and one data-plus-document pair. Disconnect SSE, refresh the browser, and verify cursor replay/session resume. Fix and rerun.

**Step 3: Round 3 — MCP/CLI and knowledge evolution**

Generate reports from CLI and MCP, verify hashes and offline opening, create a knowledge candidate, verify/supersede it, and confirm project isolation. Fix and rerun.

**Step 4: Perform visual comparison**

Capture the selected Evidence Blueprint and implementation at the same 1440×1024 state, combine them, compare hierarchy/layout/motion states, and repeat until `design-qa.md` ends with `final result: passed`.

**Step 5: Run complete verification**

```bash
python -m coverage run -m unittest discover -s tests -q
python -m coverage report --fail-under=80
python -m ruff check .
cd web
npm test -- --run
npm run typecheck
npm run build
npm audit --audit-level=high
npm run e2e -- --project=chromium
data2doc2data doctor --json
```

Expected: all suites pass, coverage remains at least 80%, downloaded reports open offline, no horizontal overflow or console errors, and the worktree contains no untracked test artifacts.

**Step 6: Commit**

Commit: `test: validate the complete live agent flow workbench`

## Completion

Completed on 2026-08-24. All eleven tasks were implemented. Three use-test rounds, full regression, visual comparison, and release diagnostics are recorded in `docs/testing/2026-08-24-agent-flow-use-tests.md` and `design-qa.md`.
