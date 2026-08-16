# Evidence Workbench and Grounded Agent Context Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Build a three-column evidence workbench and ground every Codex or WorkBuddy turn in a compact, server-generated snapshot of the current local data, deterministic analysis, and relevant document evidence.

**Architecture:** Add a provider-neutral context builder that profiles local evidence, reuses deterministic analysis results, retrieves query-specific document chunks, and renders a bounded prompt envelope. Bind the latest analysis to the browser-owned agent session, emit a safe context summary over SSE, and rebuild the static UI as a desktop workbench with accessible mobile tabs.

**Tech Stack:** Python 3.10+ standard library, dataclasses, CSV, existing retrieval/provenance engine, `unittest`, local HTTP/SSE, vanilla HTML/CSS/JavaScript.

---

### Task 1: Build the local source profile

**Files:**
- Create: `src/data2doc2data/evidence_context.py`
- Create: `tests/test_evidence_context.py`
- Modify: `src/data2doc2data/analysis.py`
- Modify: `docs/plans/task.md`

**Step 1: Write failing source-profile tests**

Cover the default demo and temporary local sources. Assert exact record count, metric names, observation dates, document count, mode, label, and source fingerprint. Assert no metric values or CSV row contents appear in serialized profile data.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/python -m unittest tests.test_evidence_context.SourceProfileTests -v`

Expected: FAIL because `data2doc2data.evidence_context` does not exist.

**Step 3: Expose validated source loading and implement the profile**

Add public wrappers in `analysis.py` for the existing fixed demo/local resolution and bounded CSV reader. Implement frozen values similar to:

```python
@dataclass(frozen=True)
class SourceProfile:
    fingerprint: str
    mode: str
    label: str
    synthetic: bool
    record_count: int
    metrics: tuple[str, ...]
    observation_dates: tuple[str, ...]
    document_count: int
    source_hashes: tuple[str, ...]
```

Compute the fingerprint from resolved paths and source hashes, never from browser input.

**Step 4: Verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_evidence_context.SourceProfileTests -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/evidence_context.py src/data2doc2data/analysis.py tests/test_evidence_context.py docs/plans/task.md
git commit -m "feat: profile local evidence sources"
```

### Task 2: Build bounded, query-specific evidence snapshots

**Files:**
- Modify: `src/data2doc2data/evidence_context.py`
- Modify: `tests/test_evidence_context.py`

**Step 1: Write failing snapshot tests**

Assert that `EvidenceContextBuilder.build(question, profile, analysis=None)` always includes source counts, retrieves only relevant document excerpts, includes a matching deterministic analysis when supplied, produces stable IDs, and never includes raw CSV rows. Use a small context budget to assert deterministic compression and preserved authoritative fields.

**Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_evidence_context.EvidenceSnapshotTests -v`

Expected: FAIL because snapshot construction is missing.

**Step 3: Implement the context builder**

Implement frozen `EvidenceSnapshot` and `ContextSummary` objects. The builder must:

- profile the saved source;
- validate an optional `InsightResult` against the current source fingerprint;
- index and rank document chunks for the current question;
- compute per-metric counts, ranges, and first/last aggregates locally;
- render a provider-neutral prompt envelope with clear `LOCAL FACTS`, `DETERMINISTIC FINDINGS`, `DOCUMENT EXCERPTS`, and `USER MESSAGE` sections;
- apply a byte budget by dropping lower-ranked excerpts only;
- set `compressed=True` when evidence is omitted;
- reject a packet whose authoritative fields alone exceed the budget.

**Step 4: Verify GREEN and privacy boundaries**

Run: `.venv/bin/python -m unittest tests.test_evidence_context -v`

Expected: PASS; explicit assertions prove fixture row strings are absent from the envelope.

**Step 5: Commit**

```bash
git add src/data2doc2data/evidence_context.py tests/test_evidence_context.py
git commit -m "feat: build bounded agent evidence snapshots"
```

### Task 3: Bind deterministic analysis and context to agent turns

**Files:**
- Modify: `src/data2doc2data/agent_api.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_agent_server.py`
- Modify: `tests/test_server.py`

**Step 1: Write failing API and provider-contract tests**

Extend the fake provider to retain the exact message it receives. Test that:

- a browser-owned analysis is registered after `/api/analyze`;
- an agent message receives a grounded envelope before the user message;
- “数据有多少？” includes `12` records, `2` metrics, `6` dates, and `1` document;
- the event stream begins with `context.attached` safe metadata;
- changing the profile invalidates the prior analysis;
- a second browser cannot reuse the first browser's analysis;
- raw fixture rows do not enter the provider message.

**Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_agent_server tests.test_server -v`

Expected: FAIL because analysis ownership and context events do not exist.

**Step 3: Implement browser-owned analysis registration**

Issue or reuse the strict browser cookie for profile and analysis requests. Add `AgentWebService.record_analysis(owner_id, result, source_fingerprint)` and clear stale records when the profile changes. Preserve non-agent analysis for callers without a browser session.

**Step 4: Ground every agent turn**

Inject `EvidenceContextBuilder` and a profile loader into `AgentWebService`. In `start_turn`, build a fresh snapshot, append:

```python
AgentEvent("context.attached", snapshot.summary.to_dict())
```

and send `snapshot.render_prompt(message)` through the existing gateway. Audit snapshot ID, counts, hashes, and compression state without recording prompt contents.

**Step 5: Verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_agent_server tests.test_server -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add src/data2doc2data/agent_api.py src/data2doc2data/server.py tests/test_agent_server.py tests/test_server.py
git commit -m "feat: ground local agent turns in evidence"
```

### Task 4: Rebuild the page as a three-column evidence workbench

**Files:**
- Modify: `src/data2doc2data/static/index.html`
- Modify: `src/data2doc2data/static/app.css`
- Modify: `src/data2doc2data/static/app.js`
- Modify: `tests/test_static_assets.py`
- Modify: `tests/test_web_demo_contract.py`
- Modify: `tests/test_web_agent_contract.py`
- Create: `tests/test_web_workbench_contract.py`

**Step 1: Write failing workbench contract tests**

Require:

- one `workbench-shell` with `data-rail`, `analysis-canvas`, and `assistant-rail`;
- a sticky status bar with active source, analysis, agent, and privacy states;
- dataset profile fields for record, metric, date, and document counts;
- a visible agent-context card with snapshot ID and compression state;
- accessible mobile tabs using buttons, `aria-selected`, and controlled panels;
- no unsafe HTML insertion.

**Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_web_workbench_contract -v`

Expected: FAIL because the workbench structure is absent.

**Step 3: Implement semantic workbench markup**

Replace the marketing-style context column and stacked panels with:

```html
<main class="workbench-shell">
  <aside id="data-workspace" class="data-rail">...</aside>
  <section id="analysis-workspace" class="analysis-canvas">...</section>
  <aside id="assistant-workspace" class="assistant-rail">...</aside>
</main>
```

Keep existing control IDs where practical to preserve behavior and accessibility.

**Step 4: Implement responsive layout and visual hierarchy**

Use a full-width app shell with roughly `280px minmax(460px, 1fr) 380px`, independent column scrolling, compact cards, and a quiet neutral palette. At `max-width: 980px`, show an accessible three-tab workspace and one active panel. Preserve reduced-motion and dark-mode behavior.

**Step 5: Wire source profile and context events**

Render source summary from the profile API. Handle `context.attached` using text nodes only, and show record/metric/document counts plus compressed state. Invalidate the displayed context immediately when the user changes or saves a source.

**Step 6: Verify GREEN**

Run: `.venv/bin/python -m unittest tests.test_static_assets tests.test_web_demo_contract tests.test_web_agent_contract tests.test_web_workbench_contract -v`

Expected: PASS.

Run: `node --check src/data2doc2data/static/app.js`

Expected: exit 0.

**Step 7: Commit**

```bash
git add src/data2doc2data/static tests/test_static_assets.py tests/test_web_demo_contract.py tests/test_web_agent_contract.py tests/test_web_workbench_contract.py
git commit -m "feat: build the evidence workbench UI"
```

### Task 5: Document grounded context and update release boundaries

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_public_metadata.py`
- Modify: `docs/plans/task.md`

**Step 1: Write failing release/documentation tests**

Require the new runtime module in the explicit bundle allowlist and require documentation for local computation, query-specific excerpts, visible compression, and provider processing boundaries.

**Step 2: Verify RED**

Run: `.venv/bin/python -m unittest tests.test_release_bundle tests.test_public_metadata -v`

Expected: FAIL because the context module and documentation are missing.

**Step 3: Update docs and the deterministic bundle allowlist**

Document the new three-column flow and explicitly state that raw CSV rows stay local while computed results and retrieved document excerpts are sent to the connected provider. Add `evidence_context.py` to the public resource allowlist without adding caches, audit stores, or tests.

**Step 4: Verify GREEN and build the release**

Run: `.venv/bin/python -m unittest tests.test_release_bundle tests.test_public_metadata -v`

Run: `.venv/bin/python scripts/build_skill_bundle.py /private/tmp/data2doc2data-workbench.zip`

Expected: tests PASS and deterministic bundle builds successfully.

**Step 5: Commit**

```bash
git add README.md CHANGELOG.md scripts/build_skill_bundle.py tests/test_release_bundle.py tests/test_public_metadata.py docs/plans/task.md
git commit -m "docs: publish grounded workbench workflow"
```

### Task 6: Run three use-test and optimization rounds

**Files:**
- Modify as required by observed failures only
- Modify: `docs/plans/task.md`

**Round 1: Core grounding and question flow**

Start the local server and test the default demo with a real available agent. Ask “数据有多少？” and “留存为什么下降？”. Verify exact source counts, grounded analysis language, no request for a file path, visible context metadata, and unchanged deterministic results. Record observations, write a failing regression test for every defect, fix, and rerun the round.

**Round 2: Source changes and boundary behavior**

Switch through all three scenarios, ask data-size and explanation questions, and verify unique snapshot IDs, correct counts, contradiction/insufficient handling, context invalidation, provider failure isolation, and approval behavior. Test an unavailable provider and a malformed local source. Add failing tests before each correction and rerun.

**Round 3: Workbench usability and responsive behavior**

Exercise the complete workflow at desktop width and 390 px: configure, analyze, connect, converse, inspect operations, approve/reject, interrupt, and switch tabs. Verify no horizontal overflow, preserved state, keyboard focus, readable scrolling, and clear busy/error states. Add failing contract or integration tests before corrections and rerun.

**Final verification**

Run:

```bash
node --check src/data2doc2data/static/app.js
.venv/bin/ruff check .
NO_PROXY=127.0.0.1 no_proxy=127.0.0.1 .venv/bin/python -m coverage run -m unittest discover -s tests -v
.venv/bin/python -m coverage report --fail-under=80
```

Expected: JavaScript and Ruff clean, all tests pass, and production coverage remains at least 80%.

Build the bundle twice and compare SHA-256 hashes. Inspect `git diff --check`, the final branch diff, and worktree status. Update `docs/plans/task.md` with exact counts and the three use-test outcomes.

**Commit final verification-only corrections**

```bash
git add <only files changed by verified corrections> docs/plans/task.md
git commit -m "test: verify grounded evidence workbench"
```
