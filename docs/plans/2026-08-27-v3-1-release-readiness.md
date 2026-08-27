# Data2Doc2Data v3.1 Release Readiness Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Deliver a public `v3.1.0` release whose CI, cold installation, real Codex/WorkBuddy/MCP journeys, artifacts, privacy boundary, and private defense demo are all verified.

**Architecture:** Keep the product architecture unchanged. Stabilize the release boundary by giving full-analysis integration requests an explicit bounded timeout, align every public version surface, build immutable artifacts, and validate the same host-owned local Agent Flow through three entry points before tagging.

**Tech Stack:** Python 3.10–3.13, `unittest`/pytest/coverage, `ThreadingHTTPServer`, GitHub Actions, uv/uvx, React/Vitest/Playwright, Codex app-server, WorkBuddy ACP/HY3, MCP stdio, offline HTML.

---

### Task 1: Make full-analysis HTTP tests deterministic without weakening fast API checks

**Files:**
- Modify: `tests/test_workbench_api.py:130-245,603-616`
- Test: `tests/test_workbench_api.py`

**Step 1: Write the failing timeout-contract test**

Add a test that patches `urlopen`, calls `request()` without an override, and asserts `timeout=2`; call it again with `timeout=15` and assert the explicit value is forwarded.

**Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_workbench_api.py -k request_timeout -q`

Expected: FAIL because `request()` does not accept a timeout override.

**Step 3: Implement the minimal helper change**

Change the helper signature to:

```python
def request(self, method, path, payload=None, cookie=None, csrf=None, timeout=2):
    ...
    with urlopen(request, timeout=timeout) as response:
        ...
```

Pass `timeout=15` only on the two requests that execute a complete flagship analysis. Do not change list, metadata, authorization, or task-loading request budgets.

**Step 4: Run targeted and full API tests**

Run: `uv run pytest tests/test_workbench_api.py -q`

Expected: all workbench API tests PASS.

**Step 5: Commit**

```bash
git add tests/test_workbench_api.py
git commit -m "test: bound full analysis integration time"
```

### Task 2: Modernize the GitHub Actions runtime while preserving the Python matrix

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_quality_contract.py`

**Step 1: Verify official action major versions**

Check the official `actions/checkout` and `actions/setup-python` repositories. Record only current supported majors that run on Node 24; do not infer versions from third-party examples.

**Step 2: Write the failing workflow contract**

Update `tests/test_quality_contract.py` to expect the verified action majors and retain the exact Python 3.10–3.13 matrix.

**Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_quality_contract.py -q`

Expected: FAIL against the old action majors.

**Step 4: Update the workflow and verify**

Modify only action majors; keep install, Ruff, coverage threshold, and duplicate non-coverage test pass unchanged.

Run: `uv run pytest tests/test_quality_contract.py -q && uv run ruff check .github tests/test_quality_contract.py`

Expected: PASS.

**Step 5: Commit**

```bash
git add .github/workflows/ci.yml tests/test_quality_contract.py
git commit -m "ci: use supported GitHub action runtimes"
```

### Task 3: Align all public metadata to v3.1.0

**Files:**
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `pyproject.toml`
- Modify: `src/data2doc2data/provenance.py`
- Modify: `src/data2doc2data/mcp_server.py`
- Modify: `src/data2doc2data/agents/codex.py`
- Modify: `src/data2doc2data/agents/workbuddy.py`
- Modify: `.codex-plugin/plugin.json`
- Modify: `.codebuddy-plugin/plugin.json`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`

**Step 1: Change release tests to require v3.1.0**

Require `3.1.0` across package metadata, engine provenance, MCP server, both host handshakes, both plugin manifests, bundle metadata, README commands, and changelog.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_release_metadata.py tests/test_release_bundle.py -q`

Expected: FAIL with remaining `3.0.0` surfaces.

**Step 3: Update production metadata and release notes**

Add a `## [3.1.0] - 2026-08-27` changelog entry covering causal communication envelopes, evidence CAS, planner recovery, protocol audit, CSRF/ReactFlow/SQLite race fixes, and release verification. Replace public build examples with `data2doc2data-v3.1.0.zip`.

**Step 4: Verify release metadata**

Run: `uv run pytest tests/test_release_metadata.py tests/test_release_bundle.py -q && uv run ruff check .`

Expected: PASS with no public runtime `3.0.0` version marker except historical changelog content.

**Step 5: Commit**

```bash
git add pyproject.toml CHANGELOG.md README.md scripts src .codex-plugin .codebuddy-plugin tests/test_release_metadata.py tests/test_release_bundle.py
git commit -m "release: prepare v3.1.0 metadata"
```

### Task 4: Build and audit public release artifacts

**Files:**
- Modify if required: `scripts/build_skill_bundle.py`
- Modify if required: `tests/test_release_bundle.py`
- Create: `docs/testing/2026-08-27-v3-1-release-readiness.md`

**Step 1: Build Python artifacts**

Run: `uv build --out-dir /tmp/ddd-v3.1.0-python-dist`

Expected: one wheel and one sdist named for `3.1.0`.

**Step 2: Build the public Skill bundle twice**

Run twice into separate temporary paths:

```bash
uv run python scripts/build_skill_bundle.py /tmp/ddd-v3.1.0-a.zip
uv run python scripts/build_skill_bundle.py /tmp/ddd-v3.1.0-b.zip
```

Expected: identical SHA-256 values and identical file listings.

**Step 3: Audit privacy and installability**

Inspect wheel, sdist, and ZIP listings. Assert no `docs/pitch`, email address, local absolute path, `.env`, credentials, `analysis_results.json`, or `run_analysis.py`. Install the wheel in an isolated uv environment and run `ddd doctor --json`.

**Step 4: Record evidence**

Write artifact names, sizes, hashes, file counts, doctor output summary, and privacy scan result into the testing document.

**Step 5: Commit**

```bash
git add docs/testing/2026-08-27-v3-1-release-readiness.md scripts/build_skill_bundle.py tests/test_release_bundle.py
git commit -m "docs: record v3.1 artifact audit"
```

### Task 5: Verify fresh GitHub installation and deterministic browser journeys

**Files:**
- Modify: `docs/testing/2026-08-27-v3-1-release-readiness.md`
- Test: `web/e2e/analysis-cycle.spec.ts`
- Test: `web/e2e/workbench.spec.ts`

**Step 1: Run local full gates**

Run: `uv run pytest && uv run ruff check .`

Run in `web/`: `npm test -- --run && npm run typecheck && npm run build && npm run e2e`

Expected: all deterministic gates PASS; only the two explicitly gated live-provider Playwright tests may skip.

**Step 2: Push the candidate branch and wait for CI**

Create a PR to `main`. Do not merge while any Python matrix job is pending or failed.

**Step 3: Cold-install the candidate commit**

Use a temporary `UV_CACHE_DIR` and config path. Run:

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data@<candidate-sha> ddd doctor --json
uvx --from git+https://github.com/BrunoBanana/data2doc2data@<candidate-sha> ddd web --no-open --port <free-port>
```

Expected: doctor healthy and HTTP 200 without using the repository `.venv`.

**Step 4: Record CI and cold-install evidence**

Append run URL, commit SHA, environment paths, HTTP result, and doctor counts to the testing document.

**Step 5: Commit the evidence update**

```bash
git add docs/testing/2026-08-27-v3-1-release-readiness.md
git commit -m "docs: verify v3.1 cold installation"
```

### Task 6: Run real Codex, WorkBuddy/HY3, and MCP acceptance journeys

**Files:**
- Modify: `docs/testing/2026-08-27-v3-1-release-readiness.md`
- Use: `src/data2doc2data/sample/cases/saas-growth-retention/`
- Use: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/`

**Step 1: Verify host readiness**

Run `codex --version`, `codebuddy --version`, host authentication diagnostics, plugin validation, and `ddd doctor --json`. Record versions without recording tokens or session IDs.

**Step 2: Run Codex connected analysis**

Use a flagship material pack but do not provide expected hypotheses. Require automatic task creation, at least two real planner decisions, local artifacts, evidence graph, and offline HTML report.

**Step 3: Run WorkBuddy/HY3 connected analysis**

Use the other material pack and explicitly select HY3 if the installed WorkBuddy supports model selection. Require the same evidence and report checks.

**Step 4: Run host-level MCP orchestration**

From a fresh host conversation, request natural-language analysis through the high-level MCP workflow without manually supplying `task_id`. Verify source recognition, task creation, analysis cycle, trace retrieval, and report generation.

**Step 5: Record bounded evidence and commit**

Record provider versions, run IDs, artifact counts, report filenames, pass/fail, and recovery behavior. Do not copy raw business data, prompts, credentials, or hidden model reasoning.

```bash
git add docs/testing/2026-08-27-v3-1-release-readiness.md
git commit -m "test: verify real v3.1 host journeys"
```

### Task 7: Update the private defense presentation only where facts changed

**Files:**
- Modify outside public Git delivery: `docs/pitch/data2doc2data-defense.html`
- Modify outside public Git delivery if used: `docs/pitch/data2doc2data-defense-detailed.html`

**Step 1: Audit the current slides**

Search for stale version, test counts, installation commands, Agent Flow diagrams, and claims about recovery or host validation.

**Step 2: Make bounded edits**

Update only factual deltas: `v3.1.0`, causal handoff envelope, evidence revisions, checkpoint/resume, current verified counts, tag-pinned install command, and real host results. Keep the 5-minute deck concise and architecture-first.

**Step 3: Verify the private HTML visually**

Open both files locally at 1440×900; check keyboard navigation, no overlap, demo link, report link, and ending slide. Confirm `git status` does not include either file.

**Step 4: Record private delivery path**

Add only a statement to the testing document that private slides were updated and excluded; do not add their contents or paths to release artifacts.

### Task 8: Tag and publish v3.1.0

**Files:**
- Modify: `docs/plans/task.md`
- Modify: `docs/testing/2026-08-27-v3-1-release-readiness.md`

**Step 1: Confirm release gate**

Require green main CI, clean worktree except known user-owned untracked files, successful artifact audit, cold install, and three host acceptance journeys.

**Step 2: Create and push an annotated tag**

```bash
git tag -a v3.1.0 -m "Data2Doc2Data v3.1.0"
git push origin v3.1.0
```

**Step 3: Verify tag-pinned cold installation**

Run `uvx --from git+https://github.com/BrunoBanana/data2doc2data@v3.1.0 ddd doctor --json` with a fresh cache and start `ddd web --no-open` on a free port.

**Step 4: Create the GitHub Release**

Attach wheel, sdist, and public Skill ZIP. Release notes must include installation, core Agent Flow changes, verification evidence, known boundaries, and SHA-256 hashes.

**Step 5: Mark task 33 complete and verify GitHub state**

Confirm Release URL, tag SHA, attached artifact names, main CI URL, and absence of private files. Update the tracker and testing report with final immutable evidence, commit those documentation updates, and publish a documentation-only follow-up if the release tag already exists.

---

Plan complete and saved to `docs/plans/2026-08-27-v3-1-release-readiness.md`.

Next step: run `.agent/workflows/execute-plan.md` to execute this plan task-by-task in single-flow mode.
