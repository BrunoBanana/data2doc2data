# Trusted Analysis and Local Agent Gateway Design

## Status

Approved on 2026-08-16.

## Objective

Upgrade Data2Doc2Data from a demonstration-oriented deterministic analyzer into a trustworthy, reproducible evidence engine, then expose that engine in the local web UI alongside locally installed Codex and Tencent WorkBuddy/CodeBuddy agents.

The evidence engine remains the authority for measured signals and validation states. Agents may interpret evidence, propose hypotheses, suggest next actions, and request file or command operations, but may not manufacture or overwrite evidence-engine conclusions.

## Goals

- Correct known signal and hypothesis-matching errors.
- Support configurable metric definitions, time windows, aggregation, and thresholds.
- Replace unordered keyword-set verification with structured hypotheses.
- Produce row-, date-, paragraph-, line-, and hash-level provenance.
- Improve local English and Chinese document retrieval without requiring hosted services.
- Add a provider-neutral gateway for Codex App Server and WorkBuddy ACP/HTTP.
- Stream agent output, diffs, command output, and approval requests into the web UI.
- Keep all data and session metadata local by default.
- Preserve a useful deterministic analysis experience when no agent is installed.

## Non-goals

- Hosted multi-user deployment.
- Silent agent startup or unattended unrestricted command execution.
- Treating an LLM response as proof that a hypothesis is supported.
- Adding external SaaS connectors in the first implementation.
- Supporting arbitrary document formats before CSV, Markdown, and text are trustworthy.

## Architecture

```text
Browser
  -> Local HTTP/SSE API
      -> Analysis Service
          -> Metric Registry
          -> Signal Engine
          -> Document Index
          -> Hypothesis Verifier
          -> Provenance Builder
      -> Agent Gateway
          -> Codex App Server Adapter
          -> WorkBuddy ACP/HTTP Adapter
          -> CLI Fallback Adapter
      -> Permission Broker
      -> Local Session/Audit Store
```

The existing loopback-only HTTP service remains the only browser-facing process. Browser code never connects directly to an agent port and never receives agent credentials or capability tokens.

## Trust Boundaries

1. CSV and document contents are untrusted user data.
2. Document text is never concatenated into system instructions. It is passed as a delimited evidence payload.
3. Provider messages and tool requests are untrusted until normalized and validated.
4. The browser may approve a pending operation but may not directly supply a shell command for execution.
5. Only the deterministic verifier can emit `supported`, `contradicted`, `mixed`, or `insufficient`.

## Analysis Domain Model

### MetricSpec

Each metric is described by:

- canonical name and aliases;
- display name and unit;
- aggregation: mean, sum, latest, minimum, or maximum;
- comparison type: split-window, previous-period, year-over-year, or explicit ranges;
- direction threshold;
- minimum observations;
- duplicate-date policy;
- optional `higher_is_better` metadata for presentation only.

CSV metrics not present in a user registry receive a conservative default spec. A metric override selects a metric; it does not silently define aggregation semantics.

### Signal

A signal records baseline and current date ranges, observation counts, aggregated values, absolute change, nullable relative change, direction, and the MetricSpec used. Non-finite numbers are rejected. When baseline is zero, relative change is `null`; direction is derived from absolute change and the configured threshold.

### DocumentChunk

Documents are indexed as chunks with source path, start/end lines, normalized text, content hash, and retrieval score. English tokenization uses normalized words. Chinese retrieval uses character bigrams/trigrams so word order is retained. The index is cached by file path, size, modification time, and SHA-256 hash.

### HypothesisSpec

A hypothesis contains one or more clauses:

```text
metric       operator/direction       time relation
activation   direction == up          same_window
retention    direction == down        same_window
```

Built-in deterministic parsers only accept unambiguous controlled patterns. Codex or WorkBuddy may propose a HypothesisSpec from natural language, but the proposal must pass schema validation and be shown to the user when ambiguity remains. Reversed subjects, reversed directions, and negated statements cannot match by sharing the same set of words or characters.

### InsightResult

The result includes:

- analysis ID and engine version;
- question and resolved metric;
- signal and MetricSpec;
- ranked document chunks and matched terms;
- hypothesis and verification details;
- validation state and confidence rationale;
- supporting, contradicting, and missing evidence;
- source hashes, row numbers, line ranges, and analysis parameters;
- recommended next verification steps;
- limitations.

## Validation Semantics

- `supported`: every required structured clause is confirmed by compatible data in the required window.
- `contradicted`: at least one required clause has sufficient data and moves in the opposite direction.
- `mixed`: evidence confirms some clauses and contradicts or cannot resolve others.
- `insufficient`: required metrics, observations, relevant documents, or an unambiguous hypothesis are missing.

Retrieval relevance is context, not causal evidence. A document match alone cannot yield `supported`.

## Agent Gateway

The provider-neutral interface exposes detection, connection, session creation/resumption, message sending, approval decisions, interruption, and health checks.

Normalized gateway events include:

- message and plan deltas;
- command output;
- file diffs;
- tool calls and results;
- approval requests;
- completion, cancellation, and errors.

### Codex Adapter

Use the local `codex app-server` JSON-RPC protocol over stdio or a Unix socket. Prefer stdio for child-process lifecycle ownership and Unix socket for an already managed daemon. Use the locally generated protocol schema to isolate experimental fields behind the adapter.

### WorkBuddy Adapter

Connect to `codebuddy --serve` through its public `/api/v1/*` endpoints and ACP JSON-RPC-over-SSE stream. Do not depend on `/internal/*`. Validate the health endpoint and public API version before creating a session.

### CLI Fallback

If a compatible streaming protocol is unavailable, optionally run `codex exec` or `codebuddy -p` in a bounded subprocess. The fallback supports text results only and clearly disables live approvals, resumable streaming, and diff events that it cannot guarantee.

## Permission Model

- **Read only:** analysis and file reads within configured roots.
- **Collaborative (default):** every write, command, or state-changing tool call requires approval.
- **Trusted session:** user may approve a specific tool, command prefix, or directory for the current session only.

Every approval card shows provider, command/tool, working directory, target paths, diff when available, and expiration. Approval grants are kept in memory and expire with the session. Dangerous global bypass flags are never exposed through the web UI.

The working root defaults to the configured evidence workspace. Additional roots require an explicit browser action. Shell environment inheritance is minimized and secrets are never copied into audit logs.

## Browser and API Design

The web UI adds provider status, provider selection, permission mode, conversation, evidence, operation, and audit panels.

Primary API surface:

- `GET /api/agents`
- `POST /api/agent-sessions`
- `POST /api/agent-sessions/{id}/messages`
- `GET /api/agent-sessions/{id}/events` (SSE)
- `POST /api/agent-sessions/{id}/approvals/{approval_id}`
- `POST /api/agent-sessions/{id}/interrupt`
- existing profile and analysis routes

Mutating requests require a short-lived, HTTP-only, same-site session cookie plus a CSRF token. Existing loopback Host and Origin checks remain in place.

## Local Persistence

Store only provider/session identifiers, selected workspace, permission mode, timestamps, normalized operation metadata, and redacted audit entries. Do not duplicate source documents into the configuration directory. Conversation persistence is opt-in unless the provider already persists the thread locally.

## Error Handling

Provider failures never make deterministic analysis unavailable. Errors are normalized into actionable states: not installed, not authenticated, incompatible version, unavailable endpoint, interrupted, approval expired, provider crash, timeout, or invalid provider payload.

Agent child processes receive startup and idle timeouts. Disconnects close open SSE streams and reject pending approvals. Unexpected provider fields are ignored unless required fields are missing. Detailed errors remain in local logs; browser messages exclude secrets and raw environment values.

## Testing Strategy

- Unit tests for finite numeric validation, zero baselines, duplicate dates, windows, aggregations, and thresholds.
- Adversarial tests for reversed directions, negation, subject swapping, Chinese word order, and prompt injection in documents.
- Golden provenance fixtures asserting row numbers, line ranges, hashes, and engine version.
- Retrieval tests for English words and Chinese n-grams with stable ranking.
- Provider contract tests against fake Codex JSON-RPC and fake WorkBuddy ACP/HTTP servers.
- Permission tests proving that writes and commands cannot run before approval.
- HTTP tests for CSRF, session cookies, origin checks, request limits, timeouts, and SSE cancellation.
- Browser tests for provider selection, streaming, approval cards, interruption, and agent-unavailable fallback.
- GitHub Actions matrix for supported Python versions plus lint, type, unit, integration, and bundle tests.

## Delivery Order

1. Establish CI and regression tests for known correctness defects.
2. Introduce MetricSpec and the corrected signal engine.
3. Add structured hypotheses and expanded validation states.
4. Add document indexing and complete provenance.
5. Introduce the provider-neutral gateway and fake-provider contract suite.
6. Implement Codex and WorkBuddy adapters.
7. Add web chat, streaming, permission, diff, and audit experiences.
8. Update documentation, Skill bundle boundaries, changelog, and release metadata.

Each stage leaves the deterministic CLI and local web analysis usable.
