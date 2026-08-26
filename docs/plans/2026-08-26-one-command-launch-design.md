# Data2Doc2Data One-Command Launch Design

**Date:** 2026-08-26

## Goal

Let a new user launch the complete local Data2Doc2Data workbench from GitHub with one memorable command after installing one lightweight runtime, without cloning the repository, creating a virtual environment, or managing Python dependencies.

## Decision

Use `uvx` as the Python-native equivalent of `npx`:

```bash
uvx --from git+https://github.com/BrunoBanana/data2doc2data ddd web
```

The command runs the GitHub package in an isolated cached environment, starts the loopback-only workbench, and opens the default browser. After a future PyPI release, the documented command can be shortened without changing the CLI contract.

We will not introduce an npm wrapper in this phase. A wrapper would add a second package, release pipeline, runtime bootstrap path, and supply-chain surface without improving the product after `uv` is installed.

## CLI Contract

- Add `ddd` as a short executable alias while preserving `data2doc2data`.
- Add `web` as the product-facing workbench command while preserving `setup` for compatibility.
- Use `127.0.0.1:8781` as the default local address.
- Open the default browser for a normal local launch.
- Support `--no-open`; retain `--no-browser` as a compatibility alias.
- Print the exact local URL whether or not a browser is opened.
- Avoid opening a browser automatically in an SSH session.

## Startup Flow

1. `uvx` obtains the package from GitHub and creates or reuses an isolated environment.
2. The `ddd` console entry point dispatches `web`.
3. DDD binds only to loopback, prepares the existing local profile and packaged demo assets, then prints the URL.
4. DDD opens the browser when appropriate and serves until interrupted.
5. The user can immediately run the deterministic demo without a model, data file, or document.

## Failure Handling

- Invalid ports fail through the existing argument parser.
- Browser launch failure does not terminate the server; the printed URL remains usable.
- SSH sessions print the URL instead of attempting to open a remote browser.
- Existing `setup --no-browser` scripts remain valid.
- Installation and dependency resolution errors remain visible as `uvx` diagnostics.

## Documentation

Place a bilingual quick-start at the top of the GitHub README:

1. Install `uv` using its official instructions.
2. Copy the single `uvx ... ddd web` command.
3. State what it does and that demo mode requires neither a model nor user data.
4. Keep developer installation, MCP registration, and agent-host integration as separate advanced sections.

Until the feature branch is merged, verification may pin the branch explicitly. The public README command must target the default branch.

## Verification

- Parser tests for `ddd web`, `--no-open`, the compatibility flags, and the 8781 default.
- Server-launch tests for browser opening, no-open behavior, SSH behavior, and browser failure.
- Package metadata test for both console entry points.
- README and release-boundary tests for the copyable GitHub command.
- A clean-cache `uvx` smoke test against the local package, followed by a real GitHub command check after the commit is pushed.
- Full backend regression suite and public-boundary checks.

