# Workbench Streaming Hardening Design

**Date:** 2026-08-22

## Goal

Make the conversational workbench remain usable during long WorkBuddy turns,
keep approvals immediately reachable, render the assistant's safe Markdown
semantically, and tighten API snapshot input boundaries.

## Approved findings

- WorkBuddy can connect and complete grounded analysis, but each streamed plan
  fragment currently creates a new operation card. A real turn produced 225
  cards and buried the approval action more than 16,000 pixels down the queue.
- The conversation scrolls only when the assistant card is created. Later
  deltas grow the card without keeping a user who was already at the bottom at
  the bottom.
- The safe Markdown renderer escapes content correctly but treats headings and
  blockquotes as plain paragraphs.
- The compact rail uses several 9–11px labels and sub-38px controls.
- API snapshots check only the initial string prefix and compose query strings
  naively; redirects and final destinations are not revalidated.

## Design

### Stream aggregation and approvals

Maintain one live operation card per event family and turn. Consecutive
`plan.delta`, `command.output`, and matching tool-result fragments append to
that card instead of creating siblings. A new tool call or terminal event ends
the current aggregation. Approval cards are inserted at the top of the queue,
focused without moving keyboard focus, and remain visible independently of
older diagnostic output.

### Conversation following

Before rendering a delta, record whether the conversation is close to its
bottom. After rendering, follow the content only for users who were already
following it. Users who scroll upward retain their position.

### Safe Markdown

Continue building DOM nodes with `textContent`; do not introduce `innerHTML`.
Add bounded support for headings, blockquotes, horizontal paragraph breaks,
and nested list indentation. Unknown syntax remains escaped text.

### Accessibility

Raise supporting text to at least 12px and compact controls to at least 38px,
with 44px targets where the layout allows. Preserve the existing semantic
regions, native controls, labels, focus ring, and reduced-motion behavior.

### API snapshot boundary

Parse URLs structurally. Require HTTPS, a hostname, no embedded credentials,
and an allowed port. Merge query parameters using parsed components. Disable
automatic redirects and follow only a small bounded number of HTTPS redirects,
revalidating every destination and refusing credential forwarding across
origins.

### WorkBuddy permission delivery

When a permission request arrives on the inline stream, yield the queued
approval immediately before reading another provider line. Keep the public
event contract unchanged.

## Testing

- Static frontend contract tests lock in aggregation, approval placement,
  intelligent scrolling, safe DOM construction, Markdown semantics, and target
  sizes.
- Python unit tests cover URL parsing, existing queries, redirect downgrade,
  redirect loops, credential stripping, and final response limits.
- WorkBuddy adapter tests simulate a provider that blocks immediately after a
  permission request.
- Full JS syntax, Ruff, unittest, coverage, browser, and live WorkBuddy checks
  close the change.

## Non-goals

- No framework or frontend dependency.
- No change to deterministic analysis authority or evidence contracts.
- No automatic approval and no wider network exposure.
