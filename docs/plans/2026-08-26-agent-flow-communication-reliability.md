# Agent Flow Communication Reliability Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Add an attributable, idempotent, conflict-safe, and resumable communication protocol to the existing DDD Agent Flow.

**Architecture:** Keep the current central planner and deterministic local tools. Extend persisted run events with a backward-compatible communication envelope, protect the evidence blackboard with compare-and-swap revisions, and project the same real protocol into the workbench and offline report.

**Tech Stack:** Python 3.10+, frozen dataclasses, SQLite/WAL, React 19, TypeScript, Vitest, pytest, Playwright.

---

### Task 1: Define the bounded communication envelope

**Files:**
- Create: `src/data2doc2data/agent_protocol.py`
- Create: `tests/test_agent_protocol.py`
- Modify: `src/data2doc2data/run_events.py`
- Modify: `tests/test_run_events.py`

**Steps:**

1. Write failing tests for required identifiers, bounded metadata, deterministic legacy defaults, serialization, duplicate message IDs, and causal references.
2. Run `uv run pytest tests/test_agent_protocol.py tests/test_run_events.py -q` and verify failure.
3. Implement `CommunicationEnvelope`, route inference, legacy restoration, and stream validation.
4. Run the focused tests and verify they pass.
5. Commit with `feat: add agent communication envelope`.

### Task 2: Attach causal routing to real flow events

**Files:**
- Modify: `src/data2doc2data/flow_engine.py`
- Modify: `tests/test_flow_engine.py`
- Modify: `tests/test_orchestrator.py`

**Steps:**

1. Write failing assertions for orchestrator-to-planner, orchestrator-to-tool, tool-to-evidence-store, and report delivery routes.
2. Run `uv run pytest tests/test_flow_engine.py tests/test_orchestrator.py -q` and verify failure.
3. Extend the engine emitter to assign message IDs, causal parents, routes, attempts, deadlines, and stable idempotency keys.
4. Verify demo and connected flows share the same protocol while identifying different planner sources.
5. Commit with `feat: trace agent flow handoffs`.

### Task 3: Version the shared evidence blackboard

**Files:**
- Modify: `src/data2doc2data/workspace_store.py`
- Modify: `src/data2doc2data/flow_engine.py`
- Modify: `tests/test_workspace_store.py`
- Modify: `tests/test_flow_engine.py`

**Steps:**

1. Write failing tests for revision creation, compare-and-swap updates, stale-writer rejection, migration from schema 4, and unchanged legacy reads.
2. Run `uv run pytest tests/test_workspace_store.py tests/test_flow_engine.py -q` and verify failure.
3. Add the schema migration, versioned artifact read, and optional expected revision.
4. Track evidence graph revision in the engine and use it for every graph mutation.
5. Run focused tests and commit with `feat: protect evidence graph revisions`.

### Task 4: Make planner retry and checkpoint semantics explicit

**Files:**
- Modify: `src/data2doc2data/cycle_runner.py`
- Modify: `src/data2doc2data/cycle_planner.py`
- Modify: `src/data2doc2data/flow_engine.py`
- Modify: `tests/test_cycle_runner.py`
- Modify: `tests/test_cycle_planner.py`

**Steps:**

1. Write failure-injection tests for transient disconnect, deadline exhaustion, bounded backoff, checkpoint emission, and completed-tool deduplication.
2. Run the focused tests and verify failure.
3. Add an injectable retry policy, clock, sleeper, deadline metadata, and checkpoint callback.
4. Ensure exhausted retries persist `waiting_for_planner` and do not re-run completed tools.
5. Run focused tests and commit with `feat: harden planner recovery protocol`.

### Task 5: Project the protocol into the workbench

**Files:**
- Modify: `web/src/contracts/run-events.ts`
- Modify: `web/src/features/flow/flow-projection.ts`
- Modify: `web/src/features/flow/FlowInspector.tsx`
- Modify: `web/src/features/flow/flow-projection.test.ts`
- Modify: `web/src/features/flow/AgentFlowCanvas.test.tsx`

**Steps:**

1. Write failing frontend tests for handoff, attempt, trace, and legacy events without communication metadata.
2. Run `npm test -- --run` from `web/` and verify failure.
3. Extend the TypeScript contract and projection with optional communication state.
4. Render compact real-protocol details without exposing raw prompts or data.
5. Run tests and typecheck; commit with `feat: expose agent protocol trace`.

### Task 6: Add the protocol audit to offline HTML reports

**Files:**
- Modify: `src/data2doc2data/reporting.py`
- Modify: `tests/test_reporting.py`
- Modify: `tests/test_mcp_server.py`

**Steps:**

1. Write failing tests for trace ID, handoff summary, attempts, and HTML escaping.
2. Run the focused reporting tests and verify failure.
3. Render a concise communication audit from persisted run events.
4. Confirm Web, CLI, and MCP report paths use the same renderer.
5. Run focused tests and commit with `feat: include protocol audit in reports`.

### Task 7: Run failure and regression verification

**Files:**
- Modify: `docs/plans/task.md`
- Modify: `docs/testing/2026-08-26-agent-flow-communication-reliability.md`

**Steps:**

1. Run `uv run ruff check src tests scripts`.
2. Run `uv run coverage run -m pytest -q && uv run coverage report`.
3. Run `npm test -- --run && npm run typecheck && npm run build` from `web/`.
4. Run the relevant Playwright workbench journey and verify no overflow or console errors.
5. Record evidence in the test report and set task 32 to completed.
6. Review the diff for private files, generated bundles, raw data, and unrelated changes.
7. Commit with `docs: record agent protocol verification`.
