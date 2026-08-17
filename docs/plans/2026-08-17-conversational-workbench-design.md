# Conversational Workbench Design

**Date:** 2026-08-17

## Goal

Reorient the workbench from a three-column form layout to a conversational
interface where:

- the primary surface is a chat-style dialog (assistant-driven),
- a side panel visualizes the deterministic evidence pipeline step by step
  (what was done, what was produced, where we are), and
- the user can inspect, amend, and re-run any step at any time.

## Principles

- The assistant (Codex / WorkBuddy) is the conversational core; the
  deterministic engine is the evidence tool the assistant's answers are
  grounded in. A deterministic conclusion is a first-class message and can
  never be overridden by assistant prose.
- Pure dialog: asking a question in the input box is the trigger. No separate
  "analyze" button is required.
- The evidence pipeline (source → signal → retrieval → verification →
  conclusion) is always visible and linked to the current turn.

## Layout

Desktop: two columns — dialog on the left, evidence pipeline on the right.
Narrow screens stack them vertically (dialog above, pipeline below). The
top bar keeps only the data-source status and the privacy boundary.

## Message kinds

- `user` — the user's question.
- `deterministic` — the engine's verdict (signal + validation), visually
  distinct and labeled as authoritative.
- `assistant` — streamed assistant explanation grounded in the evidence.
- `system` — connection state, errors, and approval cards.

## Data flow

1. User submits a question in the input box.
2. The server runs deterministic analysis (`/api/analyze`) and surfaces it as
   a `deterministic` message plus the pipeline state.
3. If an assistant session is active, the server builds the evidence snapshot
   and streams the assistant reply, attaching structured pipeline context to
   the `context.attached` event so the panel can render each step.
4. The pipeline panel reflects the current turn: source, signal, retrieved
   excerpts, verification, and final validation, each expandable and
   editable.

## Backend change

- `context.attached` currently sends only `snapshot.summary`. Extend it to
  include structured step data (source profile, metric summaries, and the
  matching deterministic analysis) so the frontend renders the pipeline
  without re-deriving it from the assistant envelope.

## Non-goals

- No new runtime dependency; no framework. Plain ES modules and the existing
  stdlib HTTP server.
- The deterministic engine and agent protocol stay unchanged; only the UI
  composition and one event payload change.
