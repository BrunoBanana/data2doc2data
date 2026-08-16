# Built-in Demo Scenario Catalog Design

## Status

Approved on 2026-08-17.

## Objective

Ship a synthetic, self-contained demonstration catalog that serves both a five-minute product walkthrough and deeper developer evaluation. The default path must remain simple, while advanced scenarios demonstrate that the evidence engine can report supported, conflicting, and insufficient outcomes without inventing certainty.

## Chosen Approach

Use a built-in scenario catalog rather than one large dataset or download-only fixtures.

- A single expanded dataset would mix unrelated stories and make expected outcomes harder to explain.
- Download-only fixtures would help developers but weaken the first-run web experience.
- A catalog keeps each story deterministic, small, independently testable, and easy to select in the local UI.

## Scenarios

### Growth quality alert

This is the default five-minute walkthrough. Activation rises while retention falls, and a strategy note explicitly says that this combination should pause acquisition expansion. The expected validation state is `supported`.

### Strategy and data conflict

A planning note predicts activation will fall while retention improves, but the measured data moves in the opposite directions. The expected validation state is `contradicted` or `mixed`, depending on clause-level results. The exact expected state is locked by a golden test.

### Insufficient evidence

The relevant strategy note requires a second metric that is absent, or the available documents have no relevant controlled hypothesis. The expected validation state is `insufficient`. The engine must explain what evidence is missing rather than silently switching scenarios or manufacturing a conclusion.

All organizations, events, people, dates, and values are fictional. Every scenario contains an explicit synthetic-data notice.

## Files and Domain Model

Store scenarios under an explicit package directory:

```text
src/data2doc2data/sample/scenarios/
  catalog.json
  growth-quality-alert/
    metrics.csv
    strategy.md
  strategy-data-conflict/
    metrics.csv
    strategy.md
  insufficient-evidence/
    metrics.csv
    strategy.md
```

`catalog.json` contains only stable presentation metadata: scenario ID, Chinese label, summary, suggested question, learning objective, and expected validation state. Code resolves file paths from a fixed registry root; catalog entries cannot point to arbitrary files.

A `DemoScenario` value object validates identifiers and metadata. `Profile` gains an optional `demo_scenario` field. Existing profiles that omit it remain valid and resolve to `growth-quality-alert`.

## Data Flow

1. `GET /api/demo-scenarios` returns safe catalog metadata without local paths.
2. The browser renders a scenario selector only while data mode is `demo`.
3. Selecting a scenario updates the suggested question but does not run analysis automatically.
4. Saving the profile persists the selected scenario ID.
5. Analysis resolves the scenario through the server-side catalog and reads its fixed CSV and Markdown files.
6. Results retain normal row, line, hash, parameter, and engine-version provenance.

Local-file mode is unchanged. Agent provider credentials and tokens remain behind the loopback server. Selecting a demo scenario does not grant an agent additional filesystem access.

## Browser Experience

The selector shows a short Chinese description and learning objective. The default scenario is suitable for a product demonstration without setup. Advanced scenarios are clearly labeled as boundary demonstrations.

The evidence engine remains visually authoritative. Agent explanations can continue from the result but cannot change its validation state.

## Error Handling

- Reject unknown or malformed scenario IDs with a validation error.
- Fail clearly when a catalog entry or required scenario file is missing.
- Do not fall back to another scenario after the user selects one.
- Preserve the existing default scenario for profiles created before this feature.
- Keep deterministic analysis available when Codex or WorkBuddy is absent.

## Release and Privacy Boundary

The release builder explicitly allowlists every catalog and scenario file. It continues to exclude user CSVs, session stores, audit logs, caches, credentials, test fixtures, and hidden files. Public-content scans cover the new documents and reject credential patterns, email addresses, and private markers.

## Testing

- Unit tests validate catalog schema, stable order, default behavior, unknown IDs, and immutable metadata.
- Golden analysis tests assert each scenario's metric, validation state, clause results, provenance hashes, rows, and line ranges.
- HTTP tests cover catalog listing, profile persistence, invalid IDs, and unchanged local-file behavior.
- Static UI tests cover accessible scenario selection, suggested-question updates, and safe `textContent` rendering.
- Bundle tests assert every synthetic scenario is included and private runtime artifacts are excluded.
- Final verification runs the complete suite twice, checks lint and JavaScript syntax, builds and inspects the release ZIP, and confirms loopback/process boundaries.
