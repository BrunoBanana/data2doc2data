# Workbench Streaming Hardening Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Keep long WorkBuddy turns, approvals, Markdown, and API data ingestion usable and safe in the local evidence workbench.

**Architecture:** Preserve the zero-build ES-module frontend and stdlib Python server. Aggregate stream fragments in the presentation layer, keep approval delivery provider-neutral, extend Markdown only through safe DOM nodes, and validate every outbound API destination before opening it.

**Tech Stack:** Python 3.11 stdlib, vanilla JavaScript ES modules, CSS, unittest, Ruff.

---

### Task 1: Stream aggregation and approval visibility

**Files:**
- Modify: `tests/test_web_agent_contract.py`
- Modify: `src/data2doc2data/static/assistant-panel.js`
- Modify: `src/data2doc2data/static/app.css`

**Steps:**
1. Add failing contracts for reusable stream cards, approval prepending, and queue following.
2. Run `python -m unittest tests.test_web_agent_contract -v` and confirm the new assertions fail.
3. Implement per-turn stream aggregation and a pinned approval area without using unsafe HTML.
4. Run the focused test and Node syntax checks.

### Task 2: Intelligent conversation following

**Files:**
- Modify: `tests/test_web_agent_contract.py`
- Modify: `src/data2doc2data/static/assistant-panel.js`

**Steps:**
1. Add a failing contract for bottom-distance detection and conditional following.
2. Confirm the test fails.
3. Implement bottom-aware scroll preservation around Markdown rendering.
4. Run the focused test.

### Task 3: Safe semantic Markdown and accessibility

**Files:**
- Modify: `tests/test_web_agent_contract.py`
- Modify: `tests/test_web_workbench_contract.py`
- Modify: `src/data2doc2data/static/ui.js`
- Modify: `src/data2doc2data/static/app.css`

**Steps:**
1. Add failing contracts for headings, blockquotes, nested list support, no `innerHTML`, 12px supporting copy, and accessible targets.
2. Confirm both focused suites fail for the missing behavior.
3. Extend the DOM-only renderer and raise compact typography/targets.
4. Run the focused tests and Node syntax checks.

### Task 4: API snapshot URL and redirect hardening

**Files:**
- Modify: `tests/test_ingestion.py`
- Modify: `src/data2doc2data/ingestion.py`

**Steps:**
1. Add failing tests for embedded credentials, missing host, non-standard ports, existing queries, HTTPS redirect validation, redirect limits, and cross-origin header stripping.
2. Run `python -m unittest tests.test_ingestion -v` and confirm the failures.
3. Implement parsed URL validation and bounded manual redirects.
4. Run the focused ingestion suites.

### Task 5: WorkBuddy permission delivery

**Files:**
- Modify: `tests/test_workbuddy_adapter.py`
- Modify: `src/data2doc2data/agents/workbuddy.py`

**Steps:**
1. Add a failing adapter test whose prompt stream pauses immediately after `session/request_permission`.
2. Confirm the approval event is not yielded by the current adapter.
3. Yield queued permission events before asking the response iterator for another line.
4. Run the focused adapter suite.

### Task 6: Regression and live verification

**Files:**
- Modify: `docs/plans/task.md`
- Modify: `CHANGELOG.md`

**Steps:**
1. Run all JavaScript syntax checks and Ruff.
2. Run the complete unittest suite and enforce 80% coverage.
3. Perform three browser rounds: long answer following, CSV mapping, and WorkBuddy approval visibility.
4. Record exact evidence in the task tracker and changelog.
