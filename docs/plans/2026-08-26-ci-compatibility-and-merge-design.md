# CI compatibility and main-merge design

## Goal

Make the existing pull request a trustworthy release candidate: preserve the documented Python 3.10–3.13 support range, remove environment-dependent test failures, eliminate duplicate pull-request runs, merge only after every required check is green, and verify that the public one-command launcher installs from `main`.

## Evidence and root causes

1. Python 3.10 rejects ISO-8601 timestamps ending in `Z` when they are passed directly to `datetime.fromisoformat`. The workspace already contains a compatible conversion, but the knowledge layer bypasses it. This creates one root failure and many downstream flow, workbench, MCP, and CLI failures.
2. Python 3.10 does not provide `tomllib`. Both production integration validation and one test import it directly even though the package declares Python 3.10 support.
3. The native-plugin launcher test assumes the checkout contains `.venv/bin/data2doc2data`. A clean CI checkout correctly falls back to the installed interpreter, so the test currently observes the developer machine rather than controlling its fixture.
4. The WorkBuddy reconnect test waits until the fake server has accepted a reconnect request, then immediately asserts that initialization and session restoration have finished. Those are different lifecycle points, producing a scheduling-dependent race. The public `detect()` method also derives readiness from the new connection ID alone, so it can report connected before restoration completes.
5. The CI workflow runs both `push` and `pull_request` jobs for the same feature-branch update.

## Considered approaches

### A. Preserve the compatibility contract (selected)

- Centralize canonical `Z` timestamp parsing and use it in validation and comparison.
- Add `tomli` only for Python versions below 3.11 and expose it through the same `tomllib` module name.
- Make launcher tests explicitly simulate whether the project virtual environment exists.
- Make reconnect tests wait for the provider's observable connected state.
- Run branch pushes only for `main`; use pull-request CI for feature branches.

This fixes causes rather than hiding failures, preserves current users, and keeps production behavior unchanged except for genuine Python 3.10 compatibility.

### B. Raise the minimum Python version to 3.11

This removes two compatibility failures but breaks the published `>=3.10` contract and does not solve the two test-isolation defects. Rejected.

### C. Remove or soften failing matrix checks

This would make the pull request appear green without establishing compatibility or reliability. Rejected.

## Detailed design

### Timestamp boundary

The workspace module remains the owner of canonical timestamps. A private parser converts the required trailing `Z` to `+00:00` before calling `datetime.fromisoformat`. Validation calls that parser, and the knowledge record invariant compares parsed values through the same function. Stored JSON remains unchanged and continues to use `Z`.

### TOML compatibility

Declare `tomli>=2` with a `python_version < '3.11'` environment marker. Production and the template-validation test import standard-library `tomllib` when available and fall back to `tomli` on Python 3.10. No optional feature may fail merely because the base interpreter is 3.10.

### Hermetic launcher test

Patch filesystem executability checks in the test that verifies project-virtual-environment preference. The test will prove selection order without requiring or creating a real `.venv`; production fallback behavior remains separately tested.

### Reconnect readiness

Keep the provider's existing reconnect sequence: reconnect, initialize, resume sessions, publish connected. Define the public `detect().connected` state as requiring both a connection ID and the existing readiness event, then change the test deadline loop to poll that state and retain the assertion that a second connection occurred. A controlled blocked-initialization test proves that an in-progress restoration remains observable as disconnected without exposing new internal synchronization APIs.

### CI event policy

Run `pull_request` for proposed changes and `push` only for `main`. A feature branch therefore receives one matrix, while the merged main branch is independently verified once.

## Verification and merge gate

1. Add or adjust focused tests first and reproduce the old failures where practical.
2. Run focused compatibility, knowledge, launcher, and WorkBuddy tests.
3. Run Ruff, coverage, the complete backend suite, frontend tests, type checking, frontend build, and package build.
4. Push the feature branch and require the full GitHub Python 3.10–3.13 matrix to pass.
5. Mark PR #1 ready and merge with a merge commit so the development history is retained.
6. Verify remote `main`, then install from a fresh `uvx` cache using the unpinned GitHub URL and run `ddd --help`. The private pitch deck, ignored deck tests, and unrelated untracked files remain local.
