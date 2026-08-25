# Agent Host Plugin Loop Design

## Goal

Turn the existing MCP server into a complete, local-first business-analysis plugin that accepts natural business requests and local sources, creates isolated tasks, lets the host agent orchestrate deterministic tools, verifies business rules, and exports one truthful, source-backed HTML report.

## Root causes established by the recorded real-host session

1. MCP exposes `run_analysis_cycle` but no task creation or source intake contract, forcing the host to import internal Python services.
2. Legacy `analyze` reads a global profile, so selecting a different case mutates unrelated user state.
3. A standalone cycle bypasses workbench runs; cycle reports call `build_html_report(task, None, None, ...)`, disconnecting real data, text, diagnostics, and report status.
4. `check_rules` validates rule syntax but never evaluates rules against locked task data.
5. Legacy analysis returns absolute source paths and every source row index, producing a very large host context.
6. Host guidance describes three legacy tools despite seven existing tools and provides no end-to-end workflow.

## Approaches considered

1. Add one monolithic tool that hides every operation. This is simple to invoke, but weakens host-agent orchestration, observability, and selective recovery.
2. Add isolated task/session tools plus one optional turnkey business-analysis tool. The host remains the reasoning agent, the project owns local computation and durable evidence, and both natural-language convenience and explicit orchestration remain available. **Selected.**
3. Start a second model-driven agent inside the MCP server. This duplicates the host agent, increases configuration cost, and complicates authorization and replay without improving deterministic evidence.

## Public plugin contract

- `inspect_sources(paths)`: classify directories, CSV, Markdown/TXT, HTML, and supported convertible documents without returning raw rows or absolute paths.
- `create_analysis_task(question, paths, title?, rules_path?)`: discover sources, lock immutable snapshots, extract embedded document tables, and create a persistent task without touching the global profile. Flagship material directories are treated as ordinary user-provided sources: Demo-only expected answers, seeded hypotheses, and solution manifests are never injected into a real host-agent task.
- `analyze_task_metric(task_id, question, metric?, rules_path?)`: run task-local evidence analysis and return compact, path-free provenance.
- `evaluate_task_rules(task_id, rules_path?)`: deterministically evaluate every declared clause against task snapshots and return explicit confirmed/contradicted/unavailable verdicts.
- `run_analysis_cycle(task_id, data_path?, document_paths?)`: infer locked task paths when omitted, preserve backward compatibility, and execute the complete workbench run so reports and trace share one state.
- `get_analysis_trace(task_id)`: return bounded task/run/cycle/event/artifact state suitable for host observation and safe continuation.
- `resume_analysis_cycle(cycle_id)`: resume durable checkpoints without replaying already completed work.
- `analyze_business_case(question, paths, title?, rules_path?, filename?)`: create task, execute the complete deterministic flow, evaluate rules, summarize all metrics, and generate the unified HTML report in one invocation.

## Data and document boundaries

All filesystem reads remain local. Host responses include source names, stable IDs, hashes, counts, bounded line ranges, aggregate metrics, and selected evidence excerpts; they exclude raw CSV records, absolute paths, credentials, and unbounded row-index arrays. Markdown, HTML, and DOCX reports can contribute both narrative and embedded structured tables; XLSX spreadsheets are parsed natively without optional dependencies. Optional PDF/legacy Office conversion remains explicit and reports an actionable diagnostic when unavailable; image-only/scanned charts are never presented as extracted facts without an installed OCR/vision adapter.

## Report and recovery model

Every complete plugin run uses the same persisted task snapshots, run events, evidence graph, analytical artifacts, rule verdicts, and report builder as the web workbench. Existing cycle reports receive task dashboards and text dashboards instead of false empty states. Task-local sessions avoid global-profile mutation; immutable snapshots, observable traces, saved cycles, and checkpoint resume provide verification, observation, and rollback/retry boundaries.

## Verification

Add failing regression tests before implementation for source intake, embedded-table reports, automatic task creation, isolated case switching, compact provenance, real rule verdicts, complete HTML reports, existing-cycle recovery, truthful report state, and updated host guidance. Run focused tests, the full Python suite, frontend unit/type/build checks, a stdio MCP end-to-end exercise using both flagship cases, and final Git/privacy audits.
