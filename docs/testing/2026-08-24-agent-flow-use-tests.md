# Agent Flow Workbench — Three Use-Test Rounds

Date: 2026-08-24  
Scope: dual-runner workbench, data-text cross reasoning, local Agent integration, offline report, CLI/MCP, and governed knowledge evolution.

## Round 1 — No-model Demo and workbench usability

- Completed both bundled flagship cases without an API or local Agent: SaaS (208 records, 4 documents) and retail (260 records, 5 documents).
- Confirmed real registered local tools emit persisted public events and construct the five-lane XYFlow canvas from an empty state. The SaaS case includes a conflict branch and converges into evidence-backed conclusions and a report.
- Verified the right Agent Console owns its viewport: message history scrolls and the composer remains fixed in normal flex layout.
- Downloaded the self-contained HTML report, opened it offline, and confirmed CSP, citations, evidence/provenance sections, and zero network requests.
- Exercised 1440 × 1024 desktop, 390 px mobile, and reduced-motion mode.

Findings fixed during this round:

1. Graph refreshes queued dozens of concurrent requests and could block report generation. Refreshes now coalesce into one active request plus one trailing refresh.
2. A terminal Demo notice remained after completion. Terminal events now clear it.
3. Most graph nodes initially fell below the first viewport. The title/KPI region, lane spacing, node width, and canvas height were compacted; node growth now triggers bounded fit-to-view.

## Round 2 — Connected Agent, bounded context, and recovery boundaries

- Mixed-source resolver, flow tools/engine, session server, Codex adapter, and WorkBuddy adapter: 56 focused Python tests passed.
- Connected the installed Tencent WorkBuddy/CodeBuddy 2.115 CLI in a fresh real-browser run. A read-only bounded task-context response completed in 6.5 seconds with no approval requests.
- Connected-mode plans are now Agent-authored and schema validated before the host executes registered local tools. Missing or invalid plans return a validation error and never fall back to the deterministic Demo plan.
- Added an explicit pure-planning instruction: the Agent must not call tools, execute commands, inspect files, or request raw rows. Any approval request fails immediately with an actionable message; provider disconnects and the 120-second timeout also surface as recoverable errors.
- Codex CLI authentication was valid, but the observed real planning turn did not terminate within the 120-second bound in this environment. The bound prevented local tool execution and Demo fallback; the tested UI failure path clears the planning state and returns an actionable retry message. This is retained as an opt-in `LIVE_CODEX_PLAN=1` compatibility probe rather than a default release gate.
- Session, cursor replay, reconnect/resume, interruption, and redacted audit behavior remain covered by the adapter/server suites.

## Round 3 — CLI/MCP reports and governed knowledge evolution

- Reporting, CLI, MCP server, host integrations, knowledge store, and workspace persistence: 38 focused Python tests passed.
- Generated the same standalone HTML report contract from Web, CLI, and MCP. Verified deterministic hashes, offline opening, provenance/citations, and absence of external resources.
- Created a project-scoped knowledge candidate, verified it, superseded it with a newer candidate, and confirmed project isolation. This evolves governed knowledge artifacts; it does not alter model weights or expose private reasoning.
- Ran `doctor --json` with an isolated clean configuration: 2 cases, 468 records, 9 documents, 4 MCP tools, source profile 12/2/1, and Codex/CodeBuddy/DeepSeek Harness templates all passed.
- The current user's pre-existing default config contains malformed source-profile JSON; it was not mutated. The isolated release configuration passed, separating environment state from product correctness.

## Final verification

- Python: 414 tests passed; coverage 86%; Ruff passed.
- Frontend: 50 Vitest tests passed; TypeScript passed; production build passed; `npm audit` reported 0 vulnerabilities.
- Browser: 5 core Chromium journeys passed; real WorkBuddy live run passed; Codex live planning probe is opt-in for the environment-dependent provider turn.
- Visual QA: normalized 1440 × 1024 comparison passed with no actionable P0/P1/P2 findings.
- Residual P3: the lazy ECharts runtime exceeds Vite's advisory 500 kB chunk warning; functionality and initial workbench interaction are unaffected.
