# CI Compatibility and Main Merge Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Make PR #1 pass its Python 3.10–3.13 matrix, merge it into `main`, and prove the public one-command install works from the default branch.

**Architecture:** Preserve the Python 3.10 contract by fixing compatibility at the timestamp and TOML boundaries. Keep production launcher and WorkBuddy reconnect behavior intact while making their tests hermetic and synchronized to public readiness, then reduce CI duplication without weakening the merge gate.

**Tech Stack:** Python 3.10–3.13, unittest, datetime, tomllib/tomli, GitHub Actions, uv/uvx, GitHub CLI.

---

### Task 1: Make canonical timestamps portable across Python 3.10–3.13

**Files:**
- Modify: `src/data2doc2data/workspace.py`
- Modify: `src/data2doc2data/knowledge.py`
- Modify: `tests/test_knowledge.py`
- Modify: `tests/test_workspace.py`

**Step 1: Add focused compatibility tests**

Add assertions that a canonical UTC timestamp ending in `Z` is accepted and parsed for invariant comparison, and that an update earlier than creation is still rejected. Exercise the shared boundary rather than calling `datetime.fromisoformat` directly.

**Step 2: Run the tests on Python 3.10 and verify the current failure**

Run: `uv run --python 3.10 python -m unittest tests.test_knowledge tests.test_workspace -v`

Expected before implementation: FAIL with `ValueError: Invalid isoformat string: '...Z'`.

**Step 3: Add one canonical parser and reuse it**

In `workspace.py`, add:

```python
def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")
```

Have `_require_timestamp` validate the type and trailing `Z`, then call this parser. Import and use the parser in `KnowledgeRecord.__post_init__` for both operands of the timestamp-order invariant. Do not change serialized timestamps.

**Step 4: Run focused tests on Python 3.10 and the current interpreter**

Run:

```bash
uv run --python 3.10 python -m unittest tests.test_knowledge tests.test_workspace -v
uv run python -m unittest tests.test_knowledge tests.test_workspace -v
```

Expected: PASS on both interpreters.

**Step 5: Commit**

```bash
git add src/data2doc2data/workspace.py src/data2doc2data/knowledge.py tests/test_knowledge.py tests/test_workspace.py
git commit -m "fix: parse canonical timestamps on Python 3.10"
```

### Task 2: Provide TOML parsing on Python 3.10

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/data2doc2data/integrations.py`
- Modify: `tests/test_integrations.py`
- Modify: `tests/test_quality_contract.py`

**Step 1: Add a dependency-contract test**

Require a `tomli` environment marker for interpreters below Python 3.11. Retain the integration-template tests that parse generated TOML.

**Step 2: Reproduce the missing-module failure on Python 3.10**

Run: `uv run --python 3.10 python -m unittest tests.test_integrations tests.test_quality_contract -v`

Expected before implementation: FAIL while importing `tomllib` or while checking the new dependency contract.

**Step 3: Add the minimal compatibility layer**

Declare:

```toml
"tomli>=2; python_version < '3.11'",
```

Use this import in production and the direct TOML-inspection test:

```python
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
```

**Step 4: Sync dependencies and run the focused suite on Python 3.10**

Run: `uv sync --extra dev && uv run --python 3.10 python -m unittest tests.test_integrations tests.test_quality_contract -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/data2doc2data/integrations.py tests/test_integrations.py tests/test_quality_contract.py
git commit -m "fix: support TOML validation on Python 3.10"
```

### Task 3: Remove environment and scheduling leaks from integration tests

**Files:**
- Modify: `src/data2doc2data/agents/workbuddy.py`
- Modify: `tests/test_integrations.py`
- Modify: `tests/test_workbuddy_adapter.py`

**Step 1: Make the native launcher fixture explicit**

In the virtual-environment preference test, patch `Path.is_file` and `os.access` to return true for the candidate launcher. Preserve the expected first candidate and command assertion, but do not require a physical project `.venv`.

**Step 2: Verify the launcher test in a clean-style environment**

Run: `uv run python -m unittest tests.test_native_plugin_launcher -v`

Expected: PASS independent of whether `.venv/bin/data2doc2data` exists.

**Step 3: Define and synchronize WorkBuddy public readiness**

Add a controlled fake-server gate that blocks reconnect initialization and proves `provider.detect().connected` remains false. Define connected as requiring both a connection ID and the provider's existing readiness event. After closing the first SSE stream, poll `provider.detect().connected` until the deadline; then assert both connected state and `fake.connect_count >= 2`, retaining the existing session-resume and event-order assertions.

**Step 4: Stress the reconnect test**

Run the focused test repeatedly:

```bash
for run in 1 2 3 4 5 6 7 8 9 10; do
  uv run python -m unittest tests.test_workbuddy_adapter.WorkBuddyAdapterTests.test_closed_sse_reconnects_and_resumes_the_existing_session -v || exit 1
done
```

Expected: 10/10 PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/agents/workbuddy.py tests/test_integrations.py tests/test_workbuddy_adapter.py docs/plans/2026-08-26-ci-compatibility-and-merge-design.md docs/plans/2026-08-26-ci-compatibility-and-merge.md
git commit -m "test: isolate launcher and reconnect readiness"
```

### Task 4: Remove duplicate pull-request matrices and run all local gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/plans/task.md`

**Step 1: Narrow push CI to main**

Change the workflow event contract to:

```yaml
on:
  push:
    branches: [main]
  pull_request:
```

This retains PR and post-merge coverage while preventing two matrices for one feature-branch push.

**Step 2: Run static and complete backend gates**

Run:

```bash
uv run ruff check .
uv run python -m coverage run -m unittest discover -s tests -v
uv run python -m coverage report --fail-under=80
uv run python -m unittest discover -s tests -v
```

Expected: all backend tests pass twice and coverage remains at least 80%.

**Step 3: Run a complete Python 3.10 gate**

Run:

```bash
uv run --python 3.10 python -m unittest discover -s tests -v
```

Expected: all backend tests pass on Python 3.10.

**Step 4: Run frontend and distribution gates**

Run:

```bash
cd web && npm test -- --run && npm run typecheck && npm run build
cd .. && uv build
```

Expected: 69 frontend tests, type checking, production build, and Python package build pass.

**Step 5: Record evidence and commit**

Append a table-only tracker entry with actual counts and commands, then commit:

```bash
git add .github/workflows/ci.yml docs/plans/task.md src/data2doc2data/static/dist
git commit -m "ci: verify supported Python releases once"
```

### Task 5: Gate, merge, and verify the default-branch installation

**Files:** None.

**Step 1: Push the feature branch**

Run: `git push origin codex/data2doc2data-optimization-pr`

Expected: PR #1 updates to the locally verified commit.

**Step 2: Wait for the complete GitHub matrix**

Run: `gh pr checks 1 --watch`

Expected: Python 3.10, 3.11, 3.12, and 3.13 jobs all pass. If any job fails, inspect its logs and return to the relevant TDD task; do not merge.

**Step 3: Mark ready and merge with history**

Run:

```bash
gh pr ready 1
gh pr merge 1 --merge
```

Expected: PR #1 is merged into `main` with a merge commit.

**Step 4: Verify remote main and the unpinned command**

Fetch `origin/main`, confirm it contains the feature head, use a fresh uv cache, and run:

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd --help
```

Expected: installation resolves from `main`, exposes `ddd web`, and exits successfully.

**Step 5: Audit delivery boundaries**

Confirm that `docs/pitch`, private defense files, ignored deck tests, `analysis_results.json`, and `run_analysis.py` are absent from the GitHub diff. Report the merge commit and exact launch command.
