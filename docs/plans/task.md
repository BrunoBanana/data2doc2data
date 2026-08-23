| # | Task | Status | Evidence |
|---:|---|---|---|
| 1 | Add CI and development quality gates | completed | 55 tests; Ruff passed; production coverage 84% |
| 2 | Lock in known correctness regressions | completed | 59 tests; zero baseline, finite values, and bilingual direction pairs covered |
| 3 | Introduce MetricSpec and signal engine | completed | 67 tests; 5 aggregations, windows, duplicates, metadata, JSON covered |
| 4 | Add structured hypothesis verification | completed | 76 tests; bilingual parsing, negation, ambiguity, schema and clause results covered |
| 5 | Add indexed retrieval and provenance | completed | 84 tests; BM25, Chinese n-grams, private cache, hashes, rows/lines and stable IDs covered |
| 6 | Define provider-neutral agent gateway | completed | 91 tests; detection, typed errors, sessions, streaming, approvals, interrupt and cleanup covered |
| 7 | Add permission broker and audit store | completed | 101 tests; roots, one-time/trusted grants, expiry, redaction and 0600 stores covered |
| 8 | Implement Codex adapter | completed | 105 tests; initialize/thread/turn, streaming, approval, crash, timeout and cleanup covered |
| 9 | Implement WorkBuddy adapter | completed | 109 tests; public ACP/HTTP, loopback binding, SSE, approval, redaction and cleanup covered |
| 10 | Expose secure session and SSE APIs | completed | 117 tests; strict cookie/CSRF, ownership, bounded SSE, approvals, limits and fallback covered |
| 11 | Build web conversation and approvals | completed | 122 tests; accessible UI, safe text rendering, SSE lifecycle, responsive layout and live Codex turn verified |
| 12 | Add validated synthetic demo scenario catalog | completed | 9 tests; strict schema, stable order/default, immutable metadata, fixed paths, missing files and symlink containment covered |
| 13 | Add synthetic scenario data and golden outcomes | completed | 37 focused tests; all fixtures are labeled synthetic, duplicate-free and locked to exact statuses, rows, line ranges and hashes |
| 14 | Persist and expose demo scenario selection | completed | 51 focused tests; old profiles default safely, selection round-trips, API metadata has no paths, and saved scenarios drive analysis |
| 15 | Build the web demo scenario experience | completed | 31 focused tests plus live browser verification; accessible safe selector, explicit-only analysis, persistence, conflict styling and 390px no-overflow layout covered |
| 16 | Update bundle, docs, and release evidence | completed | 18 release tests; 3.0.0 metadata aligned, 35-file ZIP includes complete runtime/scenarios, excludes private state, and rejects allowlisted symlinks |
| 17 | Run final regression and security verification | completed | JS/Ruff clean; 150 tests passed twice; 82% coverage; 58 security tests; deterministic 35-file ZIP SHA-256 115d1878...; boundary and branch audits clean |
| 18 | Build the local source profile | completed | 2 context tests; default demo reports 12 records, 2 metrics, 6 dates, 1 document; local fingerprints change with content |
| 19 | Build bounded query-specific evidence snapshots | completed | 6 context tests; stable IDs, stale-analysis rejection, query retrieval, deterministic compression, no raw CSV rows |
| 20 | Bind deterministic analysis and context to agent turns | completed | 31 focused tests; browser-owned analysis, isolation, invalidation, safe source-profile API and context SSE covered |
| 21 | Rebuild the page as a three-column evidence workbench | completed | 20 frontend contracts, Node syntax, Ruff, 19 agent/context tests; desktop rails, mobile tabs, source/context status and SSE resume covered |
| 22 | Document grounded context and update release boundaries | completed | 19 release/metadata tests; deterministic 36-file ZIP includes evidence context runtime and documents local/raw/provider boundaries |
| 23 | Run three use-test and optimization rounds | completed | Round 1: default 12/2/6/1 grounding and precise Codex quota error; Round 2: contradiction flow, WorkBuddy 2.115 Streamable HTTP compatibility and explicit auth state; Round 3: insufficient flow, 1280px/390px, keyboard tabs, zero overflow/console errors. JS/Ruff clean; 171 tests; 84% coverage; deterministic 36-file ZIP SHA-256 539faaa9... |
| 24 | Harden workbench streaming, approvals, Markdown, accessibility, and API snapshots | completed | 321 tests, Ruff/JS clean, 85% coverage; 3 live WorkBuddy 2.115 rounds verified Markdown + bottom follow, 12-row local-path ingestion, aggregated operations, pinned approval and successful rejection; zero browser console errors |
| 25 | Build the task-first business analysis workbench | completed | All 17 tasks and 3 optimization rounds completed: 378 Python tests at 86% coverage, 37 frontend tests, full Chromium journey plus 390px/reduced-motion and no-network offline-report checks, live WorkBuddy 2.115 read-only turn, Ruff/type/build/audit clean, partial document failures persisted through reload, and deterministic 67-file public bundle verified twice (SHA-256 1db1645c...) |
