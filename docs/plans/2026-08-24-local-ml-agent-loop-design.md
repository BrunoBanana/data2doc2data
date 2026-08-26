# Local ML Agent Loop Design

## Purpose

Data2Doc2Data must become a business-analysis task workbench whose core is auditable cross-reasoning over local structured data and text. The current system has a connected agent generate one bounded plan, then a deterministic host executes it once. The new system will add meaningful local diagnostics, local text machine learning, and a persisted analysis cycle in which an agent can revise its plan after observing derived results.

The browser remains a visualization and control surface. Raw records remain local and never enter an agent prompt.

## Decisions

- Use a host-controlled Agent Loop, not free-form generated Python or shell.
- Allow at most three rounds and twelve tool steps per round.
- Move cycle orchestration and persistence from the browser to the Python backend.
- Keep a model-free deterministic Demo policy that executes the same round protocol.
- Enable lightweight local machine learning by default; make local embedding models optional.
- Preserve the required long-form CSV fields `date`, `metric`, and `value`, while accepting additional columns as business dimensions.
- Treat word clouds as exploratory presentation, never as evidence by themselves.
- Do not claim causality from correlation, lag, clustering, or topic alignment.
- Defer forecasting, automatic model training, and causal inference to a later phase.

## Architecture

### Persisted analysis cycle

An analysis cycle owns one to three rounds. Each round contains:

- the goal and evidence gaps presented to the planner;
- a validated, acyclic tool plan;
- bounded tool arguments and stop criteria;
- local analytical artifacts;
- structured observations and limitations;
- proposed or revised hypotheses;
- the planner decision to continue or finish.

The backend runs the cycle independently of any browser connection. Browser clients subscribe to persisted run events and can reconnect after reload. The backend checks for interruption at tool boundaries and persists a checkpoint after every artifact.

Connected mode uses Codex or WorkBuddy to produce a structured round decision. Demo mode uses a deterministic policy that produces the same decision contract and the same observable event vocabulary.

### Planning protocol

The agent receives only a bounded evidence envelope containing:

- task title and goal;
- source counts, schemas, metric names, dimension names, and quality diagnostics;
- prior-round artifact summaries;
- evidence gaps and unresolved hypotheses;
- allowed tools and argument schemas;
- remaining round and resource budgets.

It returns one JSON object with an action (`continue` or `finish`), a bounded rationale suitable for audit, hypotheses, evidence gaps, stop criteria, and an optional tool plan. The rationale is an observable decision summary, not hidden chain-of-thought.

The host validates tool names, arguments, dependencies, cycle limits, input sizes, and prohibited fields. The agent cannot provide observed values or validation results.

### Local analytical table

The local table keeps the existing long format:

```csv
date,metric,value,region,channel,product
```

The first three fields remain mandatory. All additional columns are normalized as optional dimensions. Existing datasets without dimensions remain valid. Tools that require a dimension return an explicit `unavailable` result when one is absent.

All computations produce immutable analytical artifacts with:

- tool and method identifiers;
- status and bounded summary;
- observations and ranked results;
- sample size and coverage;
- parameters and deterministic seed where relevant;
- diagnostics, assumptions, and limitations;
- snapshot and source hashes;
- artifact identifier and local provenance.

Agent envelopes contain a compact projection of an artifact and never contain raw rows.

## Local computation tools

### Structured-data diagnostics

`compare_periods` calculates baseline/current values, absolute and relative changes, coverage, and comparable-window diagnostics.

`detect_anomalies` uses a robust rolling median and median absolute deviation. It reports anomaly dates, scores, local baseline, sample requirements, and degenerate-series warnings.

`detect_change_points` searches bounded split candidates for sustained level changes and reports the best supported point, effect size, before/after coverage, and method limitations.

`segment_rank` ranks dimension members by current value and change while enforcing minimum sample sizes.

`decompose_change` calculates additive contribution by a selected dimension. Rate metrics require valid numerator/denominator semantics; otherwise the tool returns `unavailable` instead of performing an invalid decomposition.

`correlate_metrics` aligns two metric series by date and evaluates zero and bounded lag relationships. It returns correlation, overlap, best lag, and a mandatory non-causality limitation.

`compare_groups` reports group differences, effect size, confidence information, sample counts, and assumptions. Insufficient or unbalanced samples produce evidence gaps rather than strong conclusions.

### Text machine learning

The default local text pipeline includes:

- Chinese-aware tokenization and TF-IDF keywords;
- deterministic SVG word-cloud data and layout;
- NMF topic discovery;
- document and paragraph clustering;
- silhouette-based bounded cluster selection;
- representative keywords, passages, and citations;
- similar-material and outlier detection;
- topic distribution by time or document metadata;
- keyword and topic trend artifacts.

An optional local Sentence Transformers adapter adds semantic search, semantic clustering, paraphrase candidates, and semantic claim alignment. If it or its local model is unavailable, the system falls back to TF-IDF/NMF and records the fallback.

### Cross-modal tools

`extract_claims` produces structured metric, direction, time, entity, and citation fields from ordinary prose in addition to explicit `主张:` lines.

`align_evidence` uses normalized aliases and structured fields instead of raw substring matching.

`compare_topics_with_metrics` aligns topic prevalence with metric series over shared periods.

`test_text_metric_lag` evaluates whether a text theme precedes or follows a metric change and states that temporal association is not causality.

`find_explanatory_segments` ranks candidate combinations of metric anomaly, business dimension, and text theme. It emits candidates for hypothesis testing, not final causal explanations.

`test_hypothesis` remains host-owned and verifies structured claims against locally computed observations.

## Cycle behavior

The initial round inspects sources, profiles data and text, and identifies candidate signals. A connected agent or Demo policy selects additional diagnostic tools. After each round, the host compacts artifacts into an evidence envelope and asks the planner to finish or revise.

A revision must refer to prior artifact identifiers and state the evidence gap it addresses. The host rejects a redundant plan that does not add a tool, parameter change, hypothesis, or new evidence target. The cycle stops when:

- the planner returns `finish` with sufficient cited artifacts;
- three rounds have completed;
- a user interrupts the run;
- no valid non-redundant plan remains;
- the provider cannot recover within its bounded wait policy.

On partial completion, the report includes completed artifacts and explicit unresolved gaps.

## Events and evidence graph

The existing run-event contract is extended with cycle and artifact events, including:

- `cycle.started` and `cycle.completed`;
- `round.started` and `round.completed`;
- `observation.created`;
- `evidence.gap.created`;
- `artifact.created`;
- `planner.waiting`, `planner.resumed`, and `planner.fallback`;
- existing `plan.created`, `plan.revised`, tool, hypothesis, validation, report, and terminal events.

Evidence nodes represent sources, compute plans, analytical artifacts, text themes, claims, hypotheses, validations, conclusions, actions, and reports. Edges retain explicit semantics such as `derived_from`, `supports`, `contradicts`, `tests`, and `insufficient_for`.

The workbench displays the observable sequence `observation → tool choice → artifact → hypothesis update → revision`. It never labels staged animation as model reasoning or exposes hidden chain-of-thought.

## Dashboard and report

The dashboard adds source-backed blocks for:

- anomaly and change-point timelines;
- contribution waterfall and segment ranking;
- correlation and lag matrix;
- group comparison with uncertainty;
- deterministic SVG word cloud;
- topic cards and cluster map;
- keyword/topic evolution;
- text-theme to metric alignment;
- cross-modal evidence matrix.

Every block links to method, parameters, sample coverage, limitations, snapshot hash, and artifacts. The offline HTML report embeds the same results without network requests and remains available from the web workbench, CLI, and MCP integration.

## Reliability and recovery

- A browser refresh replays persisted events and artifacts.
- A provider disconnect checkpoints the current round after any running local tool finishes, then waits for or resumes the provider.
- A planner timeout preserves completed artifacts and may use the deterministic fallback policy when allowed.
- Tool failure becomes a bounded artifact and evidence gap; a later round may select an alternative.
- User interruption occurs at tool boundaries and preserves completed work.
- Missing dimensions, samples, models, or comparable periods return `unavailable` or `insufficient`, never fabricated values.

## Security and privacy

- All raw tables and documents stay within approved local roots.
- Agent prompts exclude local paths, raw rows, raw documents, executable code, and shell commands.
- Plans use registered tools and bounded JSON arguments only.
- Artifact summaries are size-limited and schema-validated.
- Generated report content is escaped, content-addressed, and served with the existing offline CSP.

## Testing and acceptance

Two bundled cases will contain known anomalies, change points, dimension contributions, and document themes. Acceptance tests verify exact or bounded numeric expectations, not only rendered cards.

Required coverage includes:

- parser compatibility for dimensionless and dimensioned CSV files;
- each diagnostic algorithm on known fixtures and degenerate inputs;
- deterministic local ML output with fixed seeds;
- text citations and topic representatives;
- cross-modal alignment and mandatory non-causality limitations;
- three-round Demo behavior with actual prior-artifact references;
- connected planner validation and plan revision;
- refresh, disconnect, timeout, tool failure, fallback, and interruption recovery;
- bounded prompts that contain no raw rows or paths;
- responsive workbench presentation and readable animation;
- offline HTML report parity and no external requests;
- CLI and MCP access to analytical artifacts and report generation.

The first release is complete only when the model-free Demo, connected workbench, CLI/MCP tools, and offline report all consume the same persisted artifacts and evidence graph.
