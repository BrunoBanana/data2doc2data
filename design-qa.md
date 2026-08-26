# Agent Flow Workbench Design QA

## Comparison Target

- Source visual truth: `docs/design-references/2026-08-23/selected-evidence-blueprint.png`
- Final desktop implementation: `docs/design-references/2026-08-24/final/implementation-1440x1024.png`
- Normalized source: `docs/design-references/2026-08-24/final/reference-1440x1024.png`
- Side-by-side comparison: `docs/design-references/2026-08-24/final/comparison-2880x1024.png`

## Normalization

- Source and implementation: 1440 × 1024 at `deviceScaleFactor: 1`; combined comparison: 2880 × 1024.
- State: synthetic SaaS flagship Demo completed, all public flow events projected, evidence inspector visible, fixed Agent Console available but not connected.

## Required Fidelity Surfaces

- Fonts and typography: both use a system sans stack with heavy display headlines, compact monospaced eyebrows, readable 10–12 px metadata, and controlled Chinese wrapping. The implementation intentionally uses a larger case title than the concept image to preserve the approved Paper Neo-Brutalism hierarchy; no truncation or collision remains.
- Spacing and layout rhythm: the 220 px asset rail, flexible analysis center, and 280 px Agent Console preserve the concept's three-region structure. The compact 420 px live-canvas stage keeps the complete flow and bottom navigator in the first desktop viewport. Hard black rules, square corners, paper gutters, and green offset shadows are consistent. Desktop and 390 px mobile have zero horizontal overflow.
- Colors and visual tokens: paper `#f4f1e8`, ink `#151511`, sheet `#fffdf7`, and signal green `#08d36c` map directly across workbench and report. Semantic conflict, warning, pending, and verified states remain distinguishable.
- Image quality and asset fidelity: the visible brand uses the repository's real favicon asset rather than a text/CSS approximation. The source has no photographic product imagery. The evidence canvas is a functional XYFlow rendering, not a decorative raster substitute.
- Copy and content: labels distinguish Demo versus connected mode, Agent-authored plan, host-owned local tools, hypotheses, evidence state, assistant notes, and report export. The implementation replaces the concept's fictional warehouse tables with locked assets, public typed flow events, cross-evidence branches, and permissioned local Agent controls.
- Interaction and accessibility: onboarding modes, live node/edge growth, fit-to-view, node inspector, tabs, assistant collapse/switcher, report download, focus states, reduced motion, and mobile analysis/process/assistant views were exercised in Chromium. No console or page errors were observed.

## Comparison History

### Iteration 1 — blocked

- [P1] The evidence page jumped from the task title directly into playback, so the source design's answer-first KPI layer was missing.
- [P2] The 238/324 px side regions compressed the center, while seven graph columns caused fit-to-view nodes to become too small to read.
- Fixes: added the source-backed `数据证据摘要`, changed desktop tracks to 220/flexible/280 px, compacted the semantic graph to five columns, and bounded XYFlow zoom.
- Evidence: `implementation-qa-pass1.png` and `qa-comparison-pass1.png` before; `implementation-qa-pass2.png`, `qa-comparison-pass2.png`, and `qa-focus-header-signals-pass2.png` after.

### Iteration 2 — blocked

- [P2] The header used a text/CSS `D2` mark and the assistant empty state used a decorative CSS square instead of real assets/content.
- [P2] On mobile, a successful report-download notice remained in an absolutely positioned narrow column and could cover nearby header copy.
- Fixes: rendered the repository favicon asset, removed the decorative assistant shape, stacked mobile heading actions below the goal, and placed the report notice in normal flow at full width.
- Evidence: `implementation-qa-pass2.png` before; `implementation-qa-pass3.png` and `implementation-mobile-qa-pass4.png` after. The final mobile bounding-box check reported `overlap: false`, horizontal overflow `0`, and no console errors.

### Iteration 3 — blocked

- The first Agent Flow capture still showed a completed Demo notice and placed most graph nodes below the fold.
- Fixes: clear transient flow notices on terminal events; compact the title, tabs, KPI brief, lane spacing, and node width; reduce the canvas stage to 420 px; auto-fit after node growth.

### Iteration 4 — passed

- Recompared the complete 1440 × 1024 reference and implementation after the flow-canvas fixes.
- At least 12 live-flow nodes intersect the first viewport, the complete five-lane graph remains readable, the inspector and navigator stay usable, and the fixed Agent Console composer never leaves the viewport.
- No actionable P0, P1, or P2 differences remain. The source's warehouse content is concept material; the implementation preserves its hierarchy with actual case assets, a live Agent Flow canvas, evidence links, and local-agent controls.

## Primary Browser Interactions Tested

- Loaded each flagship case from onboarding.
- Opened data and text dashboards and verified three cited claims per case.
- Ran both no-model Demos and watched public events construct the five-lane canvas from empty state to report.
- Downloaded and opened the standalone HTML report with no external network requests.
- Switched all three 390 px mobile workspace modes with reduced motion enabled.
- Connected the installed Tencent CodeBuddy/WorkBuddy CLI in read-only mode and received bounded task context without approvals.
- Exercised connected Codex planning failure at its 120-second bound; no Demo fallback or host tool execution occurred.

## Residual P3 Polish

- The concept combines a large trend chart and evidence graph in one fixed viewport. The implementation keeps the full interactive chart in the Data/Overview tabs and retains a compact KPI scorecard in Evidence to avoid duplicating a heavy ECharts surface during playback.
- The existing ECharts runtime chunk remains above Vite's advisory 500 kB threshold; it is lazy/runtime separated and does not block functionality.

final result: passed
