# Product Hypothesis Tree Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Turn the presentation-only hypothesis tree into a source-backed product capability in the workbench and downloadable offline HTML report.

**Architecture:** Project the existing versioned evidence graph into a bounded five-stage view: task question, structured hypotheses, linked validation evidence, deterministic verdicts, and recommended next action. The React workbench renders a replayable accessible tree, while the Python report generator renders a static printable equivalent from the same node and edge semantics; neither surface exposes model-private chain-of-thought.

**Tech Stack:** Python 3.11+, escaped self-contained HTML, React 19, TypeScript, CSS animations, Vitest/Testing Library, unittest/pytest, Playwright.

---

### Task 1: Specify the workbench tree through a failing test

**Files:**
- Create: `web/src/features/evidence/HypothesisTree.test.tsx`
- Create: `web/src/features/evidence/HypothesisTree.tsx`
- Modify: `web/src/features/tasks/TaskShell.tsx`

**Step 1:** Write a test fixture with a task question, supported/contradicted/insufficient hypotheses, validation nodes, data-signal edges, conclusion, and action.

**Step 2:** Assert the rendered tree exposes all five public stages, localized statuses, explicit evidence relationships, the no-private-reasoning boundary, and a replay control.

**Step 3:** Run `npm test -- HypothesisTree.test.tsx --run` and confirm it fails because the product tree does not exist.

**Step 4:** Implement a pure graph projection and semantic React component, then mount it above the existing generic evidence graph on the task Hypothesis tab.

**Step 5:** Re-run the focused test and require a clean pass.

### Task 2: Specify the offline report tree through a failing test

**Files:**
- Modify: `tests/test_reporting.py`
- Modify: `src/data2doc2data/reporting.py`

**Step 1:** Extend the report graph fixture with source, hypothesis, validation, conclusion and action nodes plus explicit `tests`, `supports`, `contradicts`, and `insufficient_for` edges.

**Step 2:** Assert the downloaded HTML contains a semantic “假设生成与验证树”, task question, hypotheses, localized verdicts, evidence relationship labels, next action, print CSS, and no scripts or external assets.

**Step 3:** Run `.venv/bin/pytest tests/test_reporting.py -q` and confirm the new assertions fail because reports currently contain only a table.

**Step 4:** Add escaped projection helpers and responsive/printable tree styles without JavaScript or raw records.

**Step 5:** Re-run the focused report tests and require a clean pass.

### Task 3: Integrate UX, responsiveness and truthful motion

**Files:**
- Modify: `web/src/styles/app.css`
- Modify: `web/src/app/App.test.tsx`
- Modify: `web/e2e/workbench.spec.ts` or the closest existing workbench browser suite

**Step 1:** Add restrained staged reveal styles, connector lines, status colors, mobile stacking, focus states, and `prefers-reduced-motion` behavior.

**Step 2:** Verify restoration, replay, empty graphs and tasks with no hypotheses remain usable.

**Step 3:** Run `npm test -- --run`, `npm run typecheck`, `npm run build`, and the focused Playwright workbench scenario.

### Task 4: Verify and publish the public project only

**Files:**
- Verify: release bundle tests, plugin manifests, public documentation and built frontend assets.

**Step 1:** Run the full Python, frontend, browser, plugin validation and release-boundary suites.

**Step 2:** Review every tracked and untracked path; explicitly exclude `docs/pitch/`, defense-deck plans/tests, `analysis_results.json`, and `run_analysis.py`.

**Step 3:** Commit only public project files, push the existing project branch to `origin`, and verify the remote head. Do not commit or publish private presentation material.
