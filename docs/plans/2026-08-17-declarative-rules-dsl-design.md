# Declarative Rules DSL Design

**Date:** 2026-08-17

## Goal

Replace the single hard-coded dual-metric verification rule ("activation up, retention down") with a declarative, user-owned rules contract. Users (or agents proposing a hypothesis) declare the metrics that exist, how each metric is measured, and the named multi-metric rules the engine may verdict on — without editing engine code.

## Product principles

- Rules are data, not code: loaded from a bounded local JSON document, strictly validated, never executed as code.
- The built-in default ruleset reproduces historical behavior exactly when no rules file is configured.
- A document only *triggers* verification; the rule's declared directions are the contract being verified.
- Deterministic verdicts remain authoritative; rules never let an agent supply observed results.
- Validation failures are explicit, local, and never silently fall back to guessed behavior.

## Ruleset schema (version 1)

```json
{
  "version": 1,
  "metrics": {
    "revenue": {
      "aliases": ["收入", "营收"],
      "display_name": "收入",
      "unit": "元",
      "aggregation": "sum",
      "comparison": "split_window",
      "threshold": 1.0,
      "minimum_observations": 2,
      "duplicate_policy": "reject"
    }
  },
  "rules": [
    {
      "id": "revenue-churn-tradeoff",
      "name": "收入与流失权衡",
      "description": "收入上升但流失率上升时提示增长质量问题",
      "clauses": [
        { "metric": "revenue", "direction": "up" },
        { "metric": "churn_rate", "direction": "up" }
      ]
    }
  ]
}
```

### Metric definition

Each metric declares its aliases (for document phrase matching and question resolution), display name, unit, and measurement semantics. The measurement fields map one-to-one onto the existing `MetricSpec`: `aggregation` (`mean`/`sum`/`latest`/`min`/`max`), `comparison` (`split_window`/`previous_period`), `threshold` (direction threshold percent), `minimum_observations`, and `duplicate_policy` (`reject`/`mean`/`sum`).

### Rule

A rule is a named hypothesis: a set of clauses, each a metric plus an expected direction (`up`/`down`/`flat`). Rules with the same metric set are rejected, since metric set alone is the match key.

## Engine semantics

1. `parse_controlled_hypothesis` extracts metric-direction phrases from the document excerpt using the ruleset's aliases (the built-in direction vocabulary is unchanged).
2. `RuleSet.match_rule` matches the parsed hypothesis to a declared rule by metric set only — the document's phrasing is a trigger, and the rule's declared directions win.
3. `verify_hypothesis` verdicts each clause against locally computed signals; statuses are `confirmed` / `contradicted` / `unavailable`.
4. The `Verification` result now carries `rule_id` and `rule_name` when a rule matched, so the workbench and CLI can cite the specific assumption being tested.

Without a matched rule, verification falls back to the previous generic behavior over the parsed clauses.

## Validation rules

The loader rejects a ruleset before any file is trusted:

- `version` must equal 1.
- `metrics` is a non-empty object; names match `[a-zA-Z0-9_.\-]{1,128}`, are case-insensitively unique, and `aliases` is at most 12 items of at most 64 chars.
- `aggregation`/`comparison`/`duplicate_policy` are drawn from the supported sets; `threshold` is a finite non-negative number; `minimum_observations` is 2–1000.
- `rules` is at most 50 items; `id` matches `[a-zA-Z0-9_.\-]{1,64}` and is unique; `name` ≤ 128 chars; `description` ≤ 512 chars; clauses are 1–20 items with declared metrics, valid directions, and no repeated metric within a rule.
- Duplicate rule ids and duplicate metric sets are rejected.
- The file is capped at 256 KB.

## Wiring

- `analysis.analyze(..., ruleset=...)` accepts an optional `RuleSet`; absent one, `default_ruleset()` is used.
- `Profile` gains an optional `rules_path`; `validate_profile` loads and validates it early so a broken rules file fails at save time.
- CLI: `analyze --rules <path>` and `check-rules --rules <path>`.
- Server `/api/analyze` loads the profile's ruleset via `load_profile_ruleset`.

## Error handling

- Missing file, oversize, malformed JSON, and any schema violation raise `RulesError` (a subclass of `InputValidationError`), surfaced through the existing 422/exit-code-2 paths.

## Testing and acceptance

- `tests/test_rules.py` covers schema validation, matching semantics, and file loading.
- Integration tests prove the engine verdicts on metrics beyond the built-in two (e.g. `revenue`/`churn_rate`) and reports a matching `rule_id`.
- The full suite (198 tests) and coverage gate (≥80%) remain green.

## Success criteria

- A user can add a new business metric and a named rule via JSON, with no code change.
- A document mentioning the rule's metrics triggers verification and reports the rule id and name.
- Contradicting data yields `not_confirmed`; missing data yields `unavailable`.
- Configuring no rules file behaves identically to the previous version.
