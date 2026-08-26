# One-Command Workbench Launch Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Make a clean machine able to launch the complete local workbench from GitHub with `uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web`.

**Architecture:** Keep the Python package as the single runtime and expose a short `ddd` console alias. Route a new product-facing `web` command and the legacy `setup` command through one loopback launcher that prints the URL, conditionally opens the browser, and remains usable under SSH or browser-launch failure.

**Tech Stack:** Python 3.10+, argparse, stdlib HTTP server/browser integration, setuptools console scripts, uv/uvx, unittest.

---

### Task 1: Lock the CLI and package contract

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_quality_contract.py`
- Modify: `pyproject.toml`

**Step 1: Write the failing tests**

Add parser-level tests that assert `web` defaults to port `8781`, accepts `--no-open`, and maps the legacy `setup --no-browser` form to the same internal destination. Add a metadata test that expects both executables:

```python
self.assertIn('ddd = "data2doc2data.cli:main"', pyproject)
self.assertIn('data2doc2data = "data2doc2data.cli:main"', pyproject)
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_cli tests.test_quality_contract -v`

Expected: FAIL because `web`, `--no-open`, the 8781 default, and `ddd` do not exist.

**Step 3: Implement the minimal parser and metadata contract**

Add the `ddd` entry point. Introduce a shared helper that configures both subparsers:

```python
def _add_web_arguments(command: argparse.ArgumentParser, *, default_port: int) -> None:
    command.add_argument("--port", type=int, default=default_port)
    command.add_argument("--no-open", "--no-browser", dest="no_open", action="store_true")
```

Create `web` with default port `8781`; retain `setup` with its compatibility name and route both commands through the same launcher.

**Step 4: Run the focused tests**

Run: `uv run python -m unittest tests.test_cli tests.test_quality_contract -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add pyproject.toml src/data2doc2data/cli.py tests/test_cli.py tests/test_quality_contract.py
git commit -m "feat: add ddd web launch contract"
```

### Task 2: Make browser launch resilient

**Files:**
- Modify: `src/data2doc2data/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write the failing tests**

Mock the server and browser adapter. Cover:

- local `web` opens the printed URL;
- `--no-open` does not open it;
- `SSH_CONNECTION` or `SSH_CLIENT` does not open it;
- a false return or exception from `webbrowser.open` leaves the server running and returns normally after a mocked interrupt;
- the URL is always printed as `http://127.0.0.1:<actual-port>`.

**Step 2: Run tests to verify they fail**

Run: `uv run python -m unittest tests.test_cli.CliTests -v`

Expected: FAIL on SSH suppression and browser-error resilience.

**Step 3: Implement the launcher behavior**

Add small pure helpers for SSH detection and browser eligibility. Catch browser-launch exceptions separately from server startup and print a concise fallback line while continuing to serve.

**Step 4: Run the focused tests**

Run: `uv run python -m unittest tests.test_cli -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/cli.py tests/test_cli.py
git commit -m "fix: keep web launch usable without a browser"
```

### Task 3: Put the one-command path first in GitHub documentation

**Files:**
- Modify: `README.md`
- Modify: `tests/test_quality_contract.py`

**Step 1: Write the failing documentation contract**

Assert that the English and Chinese quick starts include the exact GitHub command, `uv` prerequisite, `--no-open`, `127.0.0.1:8781`, and a statement that Demo mode needs neither model nor user materials. Assert that the quick start appears before the longer developer-installation section.

**Step 2: Run the test to verify it fails**

Run: `uv run python -m unittest tests.test_quality_contract -v`

Expected: FAIL because the README still leads with manual virtualenv setup.

**Step 3: Rewrite the quick-start sections**

Lead with:

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web
```

Explain the automatic isolated installation, browser behavior, Demo readiness, and `--no-open`. Move editable installation under a developer heading and use `ddd web` in current usage examples while documenting `data2doc2data setup` as backward compatible.

**Step 4: Run the documentation and release-boundary tests**

Run: `uv run python -m unittest tests.test_quality_contract tests.test_release_bundle tests.test_public_boundary -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add README.md tests/test_quality_contract.py
git commit -m "docs: lead with one-command GitHub launch"
```

### Task 4: Verify installation from an isolated environment

**Files:**
- Modify: `docs/plans/task.md`

**Step 1: Build package artifacts**

Run: `uv build`

Expected: wheel and source distribution build successfully and contain the packaged workbench assets.

**Step 2: Smoke-test the short executable without the project environment**

Run a temporary-cache invocation against the local checkout with `ddd --help`, then launch `ddd web --no-open --port 0`, wait for the printed loopback URL, request the root page, and stop the process.

Expected: the executable resolves from the isolated environment, the HTTP response is successful, and the process stops cleanly.

**Step 3: Run the full regression gates**

Run:

```bash
uv run ruff check src tests
uv run python -m unittest discover -s tests -v
cd web && npm test -- --run && npm run typecheck && npm run build
```

Expected: all checks pass.

**Step 4: Update the task tracker**

Append a table row describing the one-command launch, isolated `uvx` smoke test, and final regression counts.

**Step 5: Commit**

```bash
git add docs/plans/task.md src/data2doc2data/static/dist
git commit -m "chore: verify one-command workbench delivery"
```

### Task 5: Push and verify the GitHub source command

**Files:** None.

**Step 1: Push the implementation branch**

Run: `git push origin codex/data2doc2data-optimization-pr`

Expected: remote branch advances without including private defense files or unrelated user files.

**Step 2: Test the pushed branch in a fresh uv cache**

Run:

```bash
UV_CACHE_DIR="$(mktemp -d)" uvx --from git+https://github.com/BrunoBanana/data2doc2data@codex/data2doc2data-optimization-pr ddd --help
```

Expected: the command installs from GitHub and lists `web`.

**Step 3: Audit the boundary**

Run: `git status --short` and inspect the pushed commit list.

Expected: only the user's existing untracked files remain; private pitch assets are ignored and absent from Git history.

