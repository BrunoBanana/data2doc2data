# Paper Analysis Desk Design QA

## Comparison Target

- Source visual truth: `docs/design-references/2026-08-23/selected-evidence-blueprint.png`
- Final desktop implementation: `docs/design-references/2026-08-23/implementation-qa-pass3.png`
- Final mobile implementation: `docs/design-references/2026-08-23/implementation-mobile-qa-pass4.png`
- Final report rendering: `docs/design-references/2026-08-23/paper-report-final.png`
- Full-view comparison: `docs/design-references/2026-08-23/qa-comparison-pass3.png`
- Focused header/signals comparison: `docs/design-references/2026-08-23/qa-focus-header-signals-pass3.png`

## Normalization

- Source pixels: 1487 × 1058.
- Implementation pixels: 1440 × 1058 at a 1440 × 1058 CSS viewport and `deviceScaleFactor: 1`.
- Comparison normalization: source scaled proportionally to 1440 × 1025 and vertically padded to 1440 × 1058; implementation retained at native capture size. The combined comparison is 2880 × 1058.
- Focus comparison: two 930 × 500 center-workspace crops combined at equal density.
- State: synthetic retail flagship case loaded, deterministic analysis completed, evidence playback paused on the first persisted event, assistant available but not connected.

## Required Fidelity Surfaces

- Fonts and typography: both use a system sans stack with heavy display headlines, compact monospaced eyebrows, readable 10–12 px metadata, and controlled Chinese wrapping. The implementation intentionally uses a larger case title than the concept image to preserve the approved Paper Neo-Brutalism hierarchy; no truncation or collision remains.
- Spacing and layout rhythm: the 220 px asset rail, flexible analysis center, and 280 px analyst margin preserve the concept's three-region structure. Hard black rules, square corners, paper gutters, and green offset shadows are consistent. Desktop and 390 px mobile have zero horizontal overflow.
- Colors and visual tokens: paper `#f4f1e8`, ink `#151511`, sheet `#fffdf7`, and signal green `#08d36c` map directly across workbench and report. Semantic conflict, warning, pending, and verified states remain distinguishable.
- Image quality and asset fidelity: the visible brand uses the repository's real favicon asset rather than a text/CSS approximation. The source has no photographic product imagery. The evidence canvas is a functional XYFlow rendering, not a decorative raster substitute.
- Copy and content: labels distinguish deterministic local computation, auditable event playback, hypotheses, evidence state, assistant notes, and report export. The implementation replaces the concept's fictional warehouse tables and approval inbox with the product's actual locked files, run events, and permissioned local assistant controls.
- Interaction and accessibility: tabs, playback, range input, speed, evidence filters, node details, assistant collapse/switcher, report download, focus states, reduced motion, and mobile analysis/process/assistant views were exercised in Chromium. No console or page errors were observed.

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

### Iteration 3 — passed

- Recompared the normalized full view and focused header/signals region after the fixes.
- No actionable P0, P1, or P2 differences remain. The source's warehouse inventory tree, dense trend chart, and approval cards are treated as concept content; the implementation preserves their hierarchy using actual case assets, a deterministic evidence scorecard, event timeline, evidence graph, and real local-agent permission controls.

## Primary Browser Interactions Tested

- Loaded each flagship case from onboarding.
- Opened data and text dashboards and verified three cited claims per case.
- Ran deterministic analysis, paused/sought/skipped playback, filtered evidence, and opened node details.
- Downloaded and opened the standalone HTML report with no external network requests.
- Switched all three 390 px mobile workspace modes with reduced motion enabled.
- Connected the installed Tencent CodeBuddy/WorkBuddy CLI in read-only mode and received bounded task context without approvals.

## Residual P3 Polish

- The concept combines a large trend chart and evidence graph in one fixed viewport. The implementation keeps the full interactive chart in the Data/Overview tabs and retains a compact KPI scorecard in Evidence to avoid duplicating a heavy ECharts surface during playback.
- The existing ECharts runtime chunk remains above Vite's advisory 500 kB threshold; it is lazy/runtime separated and does not block functionality.

final result: passed
