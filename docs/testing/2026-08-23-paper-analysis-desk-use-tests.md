# Paper Analysis Desk — Three Use-Test Rounds

Date: 2026-08-23  
Environment: macOS, Chromium via Playwright, Python 3.13 test runtime, 1440 × 1058 desktop and 390 × 844 mobile.

## Round 1 — From onboarding to evidence

Journey:

1. Open a fresh browser-owned workspace.
2. Load each complete synthetic flagship case in one click.
3. Verify data/document counts and generate the deterministic dashboard.
4. Run the automatically seeded hypotheses and inspect the persisted event track and evidence graph.

Observed:

- Both case packs loaded safely, but the evidence tab initially lacked an answer-first metric summary.
- The evidence graph fit all semantic columns at a zoom that made node labels too small.
- The rich Markdown packs showed zero extracted claims because claim paragraphs did not use the parser's explicit marker.

Optimizations:

- Added `数据证据摘要` above playback.
- Rebalanced desktop regions and compacted graph layout to five semantic columns.
- Marked three claims per case with `主张：`, retaining file/line citations.

Result: passed after focused Python, Vitest, and browser reruns.

## Round 2 — Report and real local assistant

Journey:

1. Complete the manual local-file workflow with one valid and one failing document.
2. Skip playback to the final evidence state.
3. Download the HTML report, open it from disk, and observe outgoing requests.
4. Connect the installed Tencent CodeBuddy/WorkBuddy 2.115.0 CLI in read-only mode and request bounded task context.

Observed:

- The original report visually diverged from the workbench and mixed English evidence statuses into Chinese conclusions.
- The assistant connection worked without an approval request and returned the current task plus locked-asset count.

Optimizations:

- Rebuilt the report with paper/ink/signal tokens, an answer-first conclusion, evidence scorecard, provenance, print CSS, and offline CSP.
- Localized evidence status names while preserving unknown future statuses safely.
- Added copy-ready Codex, DeepSeek Harness, and CodeBuddy configurations plus `data2doc2data doctor --json`.

Result: live WorkBuddy E2E passed in 7.0 seconds; report opened offline with no external requests.

## Round 3 — Mobile, motion, and edge states

Journey:

1. Use the full flagship flow at 390 × 844.
2. Enable `prefers-reduced-motion: reduce` and verify direct final-state rendering.
3. Switch Analysis, Process, and Assistant mobile modes.
4. Download a report and inspect notification placement, viewport overflow, and console/page errors.

Observed:

- The report success notice was constrained to the narrow desktop action column on mobile.
- The header used a text/CSS brand approximation and the empty assistant used a decorative CSS shape.

Optimizations:

- Stacked mobile actions below the business goal and made the notice full width in normal flow.
- Used the repository favicon asset and removed the decorative assistant shape.

Result: horizontal overflow `0`, notification/header overlap `false`, no browser errors, and all mobile modes remained usable.

## Automated Coverage

- Python unit/API/report/MCP/integration/release tests.
- Vitest component and app tests.
- TypeScript typecheck and production Vite build.
- Playwright: manual import, both flagship cases, three claims per case, event playback, evidence graph, offline HTML, 390 px responsiveness, reduced motion, and live WorkBuddy.
- Read-only integration doctor: 2 cases, 468 metric rows, 9 documents, MCP initialize/list/call, 3 tools, and 3 host templates.
