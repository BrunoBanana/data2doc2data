# Agent Flow Communication and Reliability Design

## Objective

Strengthen Data2Doc2Data's existing planner-and-tools architecture with an explicit communication protocol and failure semantics. The goal is not to multiply autonomous agents; it is to make every delegation attributable, every shared-state mutation conflict-safe, and every interrupted run resumable from persisted evidence.

## Decision

DDD keeps one logical orchestrator. It uses three communication patterns deliberately:

- Orchestrator-worker for agent-selected analytical tools.
- Point-to-point execution for deterministic local computation.
- A versioned evidence graph as the shared blackboard.

Broadcast chat is out of scope because it increases token use and creates unclear termination and provenance.

## Protocol

Every public run event carries a bounded `communication` envelope:

- `protocol_version`
- `message_id`
- `trace_id`
- `causation_id`
- `sender`
- `receiver`
- `attempt`
- `idempotency_key`
- `deadline_at`

The existing event `kind`, safe `summary`, and `artifact_refs` remain the business payload. Existing persisted events without an envelope are upgraded deterministically when read, so old workspaces and reports remain usable. Raw rows, local paths, prompts, and hidden chain-of-thought remain forbidden.

The `trace_id` identifies the run. `message_id` is unique within the trace. `causation_id` links a result to the command or event that caused it. Tool dispatch uses a stable idempotency key derived from cycle, round, tool, arguments, and prior artifacts.

## Shared State

The evidence graph remains the only shared analysis state. Run artifacts receive monotonically increasing revisions. Updates may include `expected_revision`; a stale writer is rejected instead of silently overwriting newer evidence. Existing read APIs continue returning only the artifact payload, while a new versioned read exposes `{revision, payload}` for the engine and diagnostics.

The flow engine tracks the evidence graph revision and performs compare-and-swap updates. This provides real dirty-write protection without introducing parallel agents or a distributed database.

## Reliability

Planner reconnection uses an explicit bounded retry policy:

- at most three attempts;
- deterministic exponential backoff with a small local budget;
- a monotonic deadline;
- observable `planner.waiting` and `planner.resumed` events including attempt and deadline metadata;
- a persisted `cycle.checkpointed` event before returning `waiting_for_planner`.

Completed tool rounds are never re-executed: their existing execution key and artifact references are replayed. A conflicting execution key remains a hard failure. Retries apply only to planner connection/read operations and immutable/idempotent local executions; arbitrary side effects are not retried.

## Projection and Delivery

The browser contract gains the optional communication envelope. The flow inspector shows the current sender-to-receiver handoff, trace identity, attempt, and artifact count from real events. HTML reports render a compact protocol audit section from persisted events. Demo mode uses the same protocol; it changes only the planner source.

The UI and reports never invent additional events or simulated agent messages.

## Error Handling

- Invalid or oversized envelopes fail at construction.
- Duplicate message IDs within one run are rejected by stream validation.
- Stale evidence revisions raise a specific workspace conflict error.
- Exhausted planner retries persist the cycle and expose a resumable checkpoint.
- Deadline expiry stops further retries immediately.
- Legacy events are upgraded without mutating their original database rows.

## Verification

Tests cover protocol validation, legacy restoration, causal stream integrity, evidence compare-and-swap, duplicate delivery, transient disconnect, deadline exhaustion, no tool re-execution after resume, frontend projection, report rendering, and full regression. Failure injection uses deterministic fake clocks and planners; tests do not depend on a live model.

## Non-goals

- No free-form multi-agent group chat.
- No distributed message broker.
- No exposure of chain-of-thought.
- No concurrent writers until a real business workflow requires them.
- No visual-only animation disconnected from persisted execution.
