# Built-in Demo Scenario Catalog Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Add a safe built-in scenario catalog for product demonstrations and developer boundary testing, then publish and verify the completed local-agent release.

**Architecture:** Add a validated `DemoScenario` registry that maps fixed IDs to package-owned synthetic CSV and Markdown files. Extend the existing profile, analysis service, loopback API, and vanilla web UI with backward-compatible scenario selection; keep local-file mode and the deterministic evidence authority unchanged.

**Tech Stack:** Python 3.10+ standard library, dataclasses, JSON, CSV, unittest, `http.server`, vanilla HTML/CSS/JavaScript, deterministic ZIP packaging.

---

### Task 1: Add the validated demo scenario registry

**Files:**
- Create: `src/data2doc2data/demo_scenarios.py`
- Create: `src/data2doc2data/sample/scenarios/catalog.json`
- Create: `tests/test_demo_scenarios.py`
- Modify: `docs/plans/task.md`

**Step 1: Write failing registry tests**

Cover stable catalog order, the `growth-quality-alert` default, safe ID validation, immutable metadata, fixed package-owned paths, missing files, and rejection of catalog path fields.

```python
catalog = DemoScenarioCatalog.load()
self.assertEqual(catalog.default.id, "growth-quality-alert")
self.assertEqual([item.id for item in catalog.list()], EXPECTED_IDS)
with self.assertRaisesRegex(DemoScenarioError, "unknown"):
    catalog.get("../../customer-data")
```

**Step 2: Run the focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_demo_scenarios -v`

Expected: FAIL because `data2doc2data.demo_scenarios` does not exist.

**Step 3: Implement the minimal registry**

Create frozen `DemoScenario` metadata and a `DemoScenarioCatalog` that reads only `sample/scenarios/catalog.json`, validates a strict ID regex, rejects unknown fields, derives `metrics.csv` and `strategy.md` paths from the ID, and verifies both files exist. Do not accept paths from JSON.

**Step 4: Run focused tests**

Run: `.venv/bin/python -m unittest tests.test_demo_scenarios -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/demo_scenarios.py src/data2doc2data/sample/scenarios/catalog.json tests/test_demo_scenarios.py docs/plans/task.md
git commit -m "feat: add validated demo scenario catalog"
```

### Task 2: Add synthetic scenario data and golden outcomes

**Files:**
- Create: `src/data2doc2data/sample/scenarios/growth-quality-alert/metrics.csv`
- Create: `src/data2doc2data/sample/scenarios/growth-quality-alert/strategy.md`
- Create: `src/data2doc2data/sample/scenarios/strategy-data-conflict/metrics.csv`
- Create: `src/data2doc2data/sample/scenarios/strategy-data-conflict/strategy.md`
- Create: `src/data2doc2data/sample/scenarios/insufficient-evidence/metrics.csv`
- Create: `src/data2doc2data/sample/scenarios/insufficient-evidence/strategy.md`
- Modify: `src/data2doc2data/analysis.py`
- Modify: `tests/test_analysis.py`
- Modify: `tests/test_demo_scenarios.py`

**Step 1: Write failing golden tests**

Assert the three scenarios resolve to `supported`, `contradicted` or the exact clause-derived conflict state, and `insufficient`. Assert each result uses the selected scenario's paths, hashes, rows, and line ranges. Assert every Markdown file contains a synthetic-data notice.

**Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_demo_scenarios tests.test_analysis -v`

Expected: FAIL because scenario files and analysis selection are absent.

**Step 3: Add minimal synthetic fixtures and analysis selection**

Keep each CSV small, finite, and duplicate-free. Use controlled hypotheses already supported by the parser. Update demo source resolution to use `DemoScenarioCatalog.get(profile.demo_scenario)` while preserving the current default result.

**Step 4: Run focused tests**

Run: `.venv/bin/python -m unittest tests.test_demo_scenarios tests.test_analysis tests.test_provenance -v`

Expected: PASS with deterministic hashes.

**Step 5: Commit**

```bash
git add src/data2doc2data/sample/scenarios src/data2doc2data/analysis.py tests/test_analysis.py tests/test_demo_scenarios.py
git commit -m "feat: add synthetic evidence demo scenarios"
```

### Task 3: Persist and expose demo scenario selection

**Files:**
- Modify: `src/data2doc2data/config.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_server.py`

**Step 1: Write failing profile and HTTP tests**

Cover old profile JSON without `demo_scenario`, round-trip persistence, invalid IDs, `GET /api/demo-scenarios`, absence of filesystem paths in its response, and unchanged local profile validation.

**Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_config tests.test_server -v`

Expected: FAIL because the profile field and endpoint are absent.

**Step 3: Implement profile and route changes**

Add `demo_scenario: str = "growth-quality-alert"` to `Profile`, validate it only through the registry for demo mode, serialize it, and return catalog presentation metadata from `GET /api/demo-scenarios`. Keep the endpoint read-only and protected by existing Host/Origin checks.

**Step 4: Run focused tests**

Run: `.venv/bin/python -m unittest tests.test_config tests.test_server tests.test_agent_server -v`

Expected: PASS; agent-unavailable fallback remains valid.

**Step 5: Commit**

```bash
git add src/data2doc2data/config.py src/data2doc2data/server.py tests/test_config.py tests/test_server.py
git commit -m "feat: expose built-in demo scenario selection"
```

### Task 4: Add the web demo scenario experience

**Files:**
- Modify: `src/data2doc2data/static/index.html`
- Modify: `src/data2doc2data/static/app.js`
- Modify: `src/data2doc2data/static/app.css`
- Modify: `tests/test_static_assets.py`
- Create: `tests/test_web_demo_contract.py`

**Step 1: Write failing static contract tests**

Assert accessible scenario selection, description and learning-objective live regions, suggested-question updates, hidden state in local mode, `/api/demo-scenarios` usage, and exclusive `textContent` rendering.

**Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_static_assets tests.test_web_demo_contract -v`

Expected: FAIL because scenario controls are absent.

**Step 3: Implement the selector**

Load scenarios on startup, render options with DOM methods, restore the saved scenario, update the suggested question only after explicit selection, include `demo_scenario` in profile saves, and preserve local path fields and existing analysis results.

**Step 4: Verify browser behavior**

Run static tests, start the loopback server, and inspect desktop plus 390px layouts. Verify switching scenarios does not run analysis automatically and local mode hides the demo selector.

**Step 5: Commit**

```bash
git add src/data2doc2data/static tests/test_static_assets.py tests/test_web_demo_contract.py
git commit -m "feat: add guided demo scenarios to web UI"
```

### Task 5: Publish versioned documentation and bundle evidence

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `CHANGELOG.md`
- Modify: `references/connector-guide.md`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_public_metadata.py`
- Modify: `tests/test_release_metadata.py`
- Modify: `pyproject.toml`
- Modify: `docs/plans/task.md`

**Step 1: Write failing release-boundary tests**

Require every new runtime module and scenario file in the explicit allowlist, reject session/audit/cache/test files, require documentation for Codex, WorkBuddy, permission modes, demo scenarios, and deterministic-authority boundaries, and require version agreement.

**Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_release_bundle tests.test_public_metadata tests.test_release_metadata -v`

Expected: FAIL because new runtime files and release metadata are missing.

**Step 3: Update release resources**

Document quick-start and advanced demos, local agent setup, WorkBuddy installation prerequisite, cold-start expectations, permissions, local persistence, and troubleshooting. Add all runtime modules and scenario resources to `PUBLIC_RESOURCE_FILES`. Bump the release to `3.0.0` across package, SkillHub metadata, Skill frontmatter, and changelog.

**Step 4: Build and inspect the release**

Run:

```bash
.venv/bin/python scripts/build_skill_bundle.py /private/tmp/data2doc2data-3.0.0.zip
unzip -l /private/tmp/data2doc2data-3.0.0.zip
```

Expected: the deterministic ZIP contains all allowlisted runtime and synthetic demo files and no logs, stores, caches, tests, credentials, or unlisted CSV files.

**Step 5: Commit**

```bash
git add README.md SKILL.md CHANGELOG.md references/connector-guide.md scripts/build_skill_bundle.py tests/test_release_bundle.py tests/test_public_metadata.py tests/test_release_metadata.py pyproject.toml docs/plans/task.md
git commit -m "docs: publish trusted local agent and demo workflow"
```

### Task 6: Run final regression and security verification

**Files:**
- Modify only files required to correct failures found during verification.
- Modify: `docs/plans/task.md`

**Step 1: Run syntax, lint, and the full suite twice**

Run:

```bash
node --check src/data2doc2data/static/app.js
.venv/bin/ruff check .
NO_PROXY=127.0.0.1 no_proxy=127.0.0.1 .venv/bin/python -m unittest discover
NO_PROXY=127.0.0.1 no_proxy=127.0.0.1 .venv/bin/python -m unittest discover
```

Expected: both runs PASS with no resource warnings, ordering dependency, or leaked child processes.

**Step 2: Run coverage and boundary tests**

Run coverage with `--fail-under=80`. Reconfirm loopback-only HTTP, provider endpoint validation, Cookie/CSRF ownership, expired approvals, child-process cleanup, public-content scans, and scenario path containment.

**Step 3: Build and inspect the final bundle**

Build `/private/tmp/data2doc2data-final.zip`, list every entry, scan names for `.env`, logs, sessions, audit, cache, test fixtures, and user data, and verify deterministic rebuild hashes.

**Step 4: Review the branch**

Run `git diff --check`, `git status --short`, and `git log --oneline --decorate -20`. Confirm one focused commit per task and no unintended files.

**Step 5: Record completion**

Mark the final tracker row complete with exact test count, coverage, bundle hash, and live Codex evidence. Commit verification-only corrections if any.
