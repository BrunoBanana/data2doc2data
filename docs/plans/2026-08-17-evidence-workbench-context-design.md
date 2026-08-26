# Evidence Workbench and Grounded Agent Context Design

**Date:** 2026-08-17

## Goal

Turn the existing vertically stacked setup page into a focused three-column evidence workbench, and ensure locally connected Codex or Tencent WorkBuddy/CodeBuddy sessions receive a trustworthy, compact representation of the current data and analysis instead of an ungrounded user message.

## Product principles

- Raw CSV data is analyzed locally by the deterministic engine.
- Agents receive the minimum sufficient evidence for the current question, not the complete raw dataset.
- Deterministic findings remain authoritative and visually separate from agent explanations.
- Every agent turn shows what evidence was attached, whether it was compressed, and which snapshot it came from.
- Changing the source or demo scenario invalidates stale context.
- Agent failures never remove or overwrite deterministic analysis results.
- Desktop uses a three-column workbench; narrow screens use Data, Analysis, and Assistant tabs.

## Workbench information architecture

### Top status bar

The top bar shows the product identity, active source or scenario, local analysis state, agent connection state, and a concise privacy boundary. It remains visible while the user works.

### Left column: data

The data column owns source mode, scenario selection, local paths, save state, and a dataset profile. Once a source is valid, the profile shows record count, metric count, date range, document count, and whether the data is synthetic or local.

### Center column: analysis

The center column is the primary canvas. It contains the business question, optional metric override, analysis action, and results organized as signal, document context, verification, final validation, evidence, and limitations. The deterministic result is never rendered as assistant output.

### Right column: assistant

The assistant column contains provider and permission controls, a visible context attachment summary, the conversation, and a separate operation/approval view. The user can see the number of computed records, metrics, and document excerpts attached to the current turn.

On narrow screens these columns become three accessible tabs. Selecting a tab changes only presentation; state and in-flight work are preserved.

## Trusted context architecture

### Local source profile

The server derives a source profile from the saved profile and its resolved package-owned or local paths. It computes:

- source mode and safe display label;
- CSV record count, metric names, and date range;
- document count;
- source hashes;
- synthetic-data status.

The profile contains no raw CSV rows.

### Evidence snapshot

An evidence snapshot is created for each agent turn from server-owned state. It contains:

- a stable snapshot ID and engine version;
- the source profile;
- the current user question;
- the latest deterministic analysis result when one exists and still matches the current source;
- locally computed metric summaries needed for the question;
- relevant document excerpts with paths, hashes, and line ranges;
- limitations and an explicit statement that agent text cannot replace deterministic validation.

The browser may reference an analysis ID, but it cannot submit or override deterministic findings. The server rebuilds and validates the snapshot from the saved profile and local evidence.

### Per-turn retrieval and multi-turn behavior

Every message triggers local retrieval against the current document index. The first turn includes the source profile and relevant evidence. Later turns reuse stable source metadata and add only the evidence relevant to the new question. Conversation history remains provider-managed, while the evidence header makes the current grounding explicit.

Questions that do not identify a metric, such as “数据有多少？”, still receive the source profile. Questions that identify a metric also receive its local statistical summary and, when possible, a deterministic analysis result.

### Context budgeting

The context builder uses a deterministic byte budget. It preserves, in order:

1. source profile and record counts;
2. deterministic validation and limitations;
3. provenance and source hashes;
4. metric summaries;
5. highest-ranked document excerpts.

If the full packet exceeds the budget, lower-ranked excerpts are omitted and the packet is marked compressed. Raw rows are never silently substituted for computed results. If the required authoritative fields alone exceed the budget, the provider call is blocked with a local error.

### Provider-neutral prompt envelope

Codex and WorkBuddy receive the same text envelope before the user's message. The envelope labels local facts, deterministic findings, retrieved excerpts, compression status, and behavioral constraints. Provider adapters remain responsible only for protocol translation.

## Data flow

1. The browser loads the saved profile and a safe source summary.
2. The user saves or changes the source; the server validates it and invalidates stale analysis snapshots.
3. The user optionally runs deterministic analysis; the server returns and remembers the result for that browser session and source fingerprint.
4. The user sends an agent message.
5. The server builds a fresh evidence snapshot from the saved source, latest matching analysis, and query-specific retrieval.
6. The server records safe snapshot metadata, then sends the provider-neutral envelope and user message through the selected adapter.
7. The browser receives the context summary and provider events over the existing event stream.

## Privacy and security

- CSV rows remain local; only derived statistics and counts enter the agent context.
- Only retrieved document excerpts enter the context, within existing file and directory limits.
- Snapshot construction uses fixed demo paths or validated local paths from the server profile.
- Browser ownership, CSRF, workspace containment, approval expiry, audit redaction, and child-process cleanup remain unchanged.
- Snapshot audit records include IDs, counts, hashes, and compression state, not raw context text.
- The UI states that selected excerpts and computed results are sent to the connected provider under that provider's account and data policy.

## Error handling

- Missing or invalid sources prevent context construction and provider invocation.
- A source change invalidates the latest analysis and forces a new snapshot.
- Retrieval failure produces a local error without discarding an existing deterministic result.
- Provider timeout, disconnect, or malformed events affect only the assistant column.
- Context compression is visible in the assistant column.
- Empty or ambiguous questions still receive the source profile; deterministic metric analysis is included only when valid.

## Testing and acceptance

- Unit tests cover exact record, metric, date-range, and document counts.
- Privacy tests prove raw CSV rows are absent from provider context.
- Retrieval and budgeting tests cover query-specific excerpts, stable ordering, compression, and hard failures.
- API tests cover browser ownership, source fingerprints, stale-analysis invalidation, and context-summary events.
- Provider contract tests prove Codex and WorkBuddy receive the same evidence envelope.
- Static UI tests cover the three-column workbench, context status, safe text rendering, and narrow-screen tabs.
- Live browser testing covers desktop and 390 px widths.
- Three end-to-end use rounds cover data-size questions, evidence explanations, source switching, agent unavailability, approvals, and responsive behavior. Findings from each round are fixed and re-tested before completion.

## Success criteria

- “数据有多少？” returns the current source profile without asking for a file path.
- The default demo reports 12 records, 2 metrics, 6 dates, and 1 document.
- Switching scenarios changes the next turn's source profile and snapshot ID.
- Raw CSV rows are not present in provider prompts.
- Deterministic analysis works when no agent is installed.
- The desktop experience reads as one coordinated workbench rather than stacked setup forms.
