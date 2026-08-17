# Evidence Contract Versioning Design

**Date:** 2026-08-17

## Goal

Give the cross-harness evidence envelope an explicit, machine-checkable version so that WorkBuddy, DeepSeek harness, Codex, and future consumers can detect contract drift instead of silently misreading a changed envelope.

## Decision

- Introduce `CONTRACT_VERSION = 1` in `evidence_context.py`.
- Stamp the version in two places:
  1. The first line of every prompt envelope: `EVIDENCE CONTRACT v1`.
  2. `ContextSummary.contract_version`, which flows through `to_dict()` into the workbench `context.attached` event.
- The version counts against the context byte budget, so a consumer can rely on its presence without silently exceeding a budget.
- Bump `CONTRACT_VERSION` only when the envelope layout or `ContextSummary` schema changes in a way a consumer must know about.

## Semantics

- The envelope header is informational for providers but authoritative for humans debugging a conversation: it makes the exact grounding contract visible.
- `ContextSummary.contract_version` is the structured signal a harness can branch on.

## Non-goals

- This is not a wire protocol handshake; providers do not negotiate a version.
- The version does not cover the deterministic analysis schema (that is versioned separately via `provenance.engine_version`).

## Acceptance

- Every built snapshot's envelope starts with `EVIDENCE CONTRACT v1`.
- `snapshot.summary.contract_version == 1` and appears in `summary.to_dict()`.
- The existing byte-budget and compression tests still pass.
