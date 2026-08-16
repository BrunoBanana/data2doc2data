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
| 12 | Add validated synthetic demo scenario catalog | pending | |
| 13 | Add synthetic scenario data and golden outcomes | pending | |
| 14 | Persist and expose demo scenario selection | pending | |
| 15 | Build the web demo scenario experience | pending | |
| 16 | Update bundle, docs, and release evidence | pending | |
| 17 | Run final regression and security verification | pending | |
