# Local ML Agent Loop Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Build a persisted, maximum-three-round Agent Loop that runs source-backed business diagnostics and local text machine learning without sending raw data to Codex or WorkBuddy.

**Architecture:** The Python host owns normalized analytical tables, immutable artifacts, registered tools, cycle persistence, recovery, and reporting. Demo and connected planners share one round-decision contract; connected providers receive only compact artifact projections. React subscribes to persisted events and renders analytical artifacts rather than inventing presentation-only reasoning.

**Tech Stack:** Python 3.10+, SQLite, scikit-learn, jieba, React 19, TypeScript, ECharts, Vitest, Playwright, pytest/unittest.

---

### Task 1: Dimension-aware analytical table

**Files:**
- Create: `src/data2doc2data/analytical_table.py`
- Create: `tests/test_analytical_table.py`
- Modify: `src/data2doc2data/data_profile.py`
- Modify: `src/data2doc2data/flow_tools.py`

**Step 1: Write failing compatibility and dimension tests**

```python
def test_loads_required_long_form_without_dimensions(tmp_path):
    path = write_csv(tmp_path, "date,metric,value\n2026-01-01,gmv,10\n")
    table = load_analytical_table(path, "snapshot-1")
    assert table.dimensions == ()
    assert table.rows[0].dimensions == {}


def test_preserves_optional_dimensions_and_rejects_reserved_or_missing_fields(tmp_path):
    path = write_csv(
        tmp_path,
        "date,metric,value,region,channel\n2026-01-01,gmv,10,华东,直播\n",
    )
    table = load_analytical_table(path, "snapshot-1")
    assert table.dimensions == ("region", "channel")
    assert table.rows[0].dimensions == {"region": "华东", "channel": "直播"}
```

**Step 2: Run tests and verify RED**

Run: `uv run pytest tests/test_analytical_table.py -q`

Expected: FAIL because `data2doc2data.analytical_table` does not exist.

**Step 3: Implement the immutable table contract**

Create `AnalyticalRow`, `AnalyticalTable`, and `load_analytical_table`. Enforce required fields, finite values, ISO dates, bounded column names, bounded rows, normalized metric names, SHA-256 provenance, and immutable dimension mappings. Update profiling and local tools to use this parser without changing the existing dashboard contract.

**Step 4: Run focused and regression tests**

Run: `uv run pytest tests/test_analytical_table.py tests/test_data_profile.py tests/test_flow_tools.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/analytical_table.py src/data2doc2data/data_profile.py src/data2doc2data/flow_tools.py tests/test_analytical_table.py
git commit -m "feat: preserve business dimensions in analytical tables"
```

### Task 2: Period comparison, anomaly detection, and change points

**Files:**
- Create: `src/data2doc2data/diagnostics.py`
- Create: `tests/test_diagnostics.py`

**Step 1: Write failing tests against known series**

```python
def test_compare_periods_reports_auditable_change():
    artifact = compare_periods(series([10, 10, 12, 14]), split=2)
    assert artifact.observations["baseline"] == 10
    assert artifact.observations["current"] == 13
    assert artifact.observations["change_percent"] == 30
    assert artifact.sample_size == 4


def test_detect_anomalies_finds_robust_spike_without_calling_trend_anomaly():
    artifact = detect_anomalies(series([10, 10, 11, 10, 10, 50, 11, 10]), window=5)
    assert [item["index"] for item in artifact.observations["anomalies"]] == [5]


def test_detect_change_point_finds_sustained_level_shift():
    artifact = detect_change_points(series([10] * 8 + [20] * 8), minimum_window=4)
    assert artifact.observations["change_index"] == 8
    assert artifact.observations["effect_size"] > 1
```

Also test constant series, too few samples, zero baselines, duplicate dates, and invalid parameters.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_diagnostics.py -q`

Expected: FAIL because the diagnostic functions do not exist.

**Step 3: Implement deterministic diagnostic artifacts**

Implement `AnalyticalArtifact`, `SeriesPoint`, `compare_periods`, rolling-median/MAD `detect_anomalies`, and bounded split-search `detect_change_points`. Every artifact must include method, sample size, parameters, diagnostics, limitations, and source refs. Use deterministic ordering and no random state.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/test_diagnostics.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/data2doc2data/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add robust local time-series diagnostics"
```

### Task 3: Segment ranking and valid contribution decomposition

**Files:**
- Modify: `src/data2doc2data/diagnostics.py`
- Modify: `tests/test_diagnostics.py`

**Step 1: Write failing dimension tests**

```python
def test_decompose_additive_change_by_channel():
    artifact = decompose_change(table_with_channel_gmv(), metric="gmv", dimension="channel")
    assert artifact.status == "completed"
    assert artifact.observations["contributors"][0]["member"] == "直播"
    assert sum(item["delta"] for item in artifact.observations["contributors"]) == artifact.observations["total_delta"]


def test_refuses_to_decompose_rate_without_numerator_and_denominator():
    artifact = decompose_change(table_with_channel_rate(), metric="refund_rate", dimension="channel")
    assert artifact.status == "unavailable"
    assert "numerator" in artifact.limitations[0]
```

Test missing dimensions, sparse groups, ties, and deterministic ranking.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_diagnostics.py -q`

Expected: FAIL because segment functions are missing.

**Step 3: Implement `segment_rank` and `decompose_change`**

Support additive metrics first. Accept explicit rate semantics only when numerator and denominator metrics are provided. Return evidence gaps for invalid decompositions rather than best-effort numbers.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_diagnostics.py -q`

```bash
git add src/data2doc2data/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add segment contribution diagnostics"
```

### Task 4: Correlation, bounded lag, and group comparison

**Files:**
- Modify: `src/data2doc2data/diagnostics.py`
- Modify: `tests/test_diagnostics.py`

**Step 1: Write failing statistical tests**

```python
def test_correlation_reports_best_lag_and_non_causality_limit():
    artifact = correlate_metrics(leading_series(), lagging_series(), max_lag=3)
    assert artifact.observations["best_lag"] == 1
    assert artifact.observations["correlation"] > 0.9
    assert any("caus" in item.lower() or "因果" in item for item in artifact.limitations)


def test_group_comparison_reports_effect_and_interval():
    artifact = compare_groups([10, 11, 9, 10, 10], [15, 14, 16, 15, 15])
    assert artifact.observations["effect_size"] > 2
    assert artifact.observations["confidence_interval"][1] < 0
```

Test insufficient overlap, constant series, missing values, and unbalanced groups.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_diagnostics.py -q`

**Step 3: Implement aligned Pearson/Spearman-style summaries, lag search, Welch effect diagnostics, and deterministic bootstrap confidence intervals**

Use a fixed seed derived from artifact inputs. Report overlap and assumptions. Never emit causal language.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_diagnostics.py -q`

```bash
git add src/data2doc2data/diagnostics.py tests/test_diagnostics.py
git commit -m "feat: add relationship and group diagnostics"
```

### Task 5: Default local text ML and deterministic word cloud

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `src/data2doc2data/text_ml.py`
- Create: `tests/test_text_ml.py`

**Step 1: Add failing local-ML tests**

```python
def test_text_pipeline_discovers_two_topics_with_representative_citations():
    result = analyze_text_corpus(two_topic_corpus(), seed=7)
    assert len(result.topics) == 2
    assert {topic.label for topic in result.topics} == {"交付问题", "价格问题"}
    assert all(topic.representatives[0].citation.start_line for topic in result.topics)


def test_word_cloud_is_deterministic_offline_svg():
    first = build_word_cloud_svg({"退款": 10, "延迟": 7}, width=640, height=320, seed=7)
    second = build_word_cloud_svg({"退款": 10, "延迟": 7}, width=640, height=320, seed=7)
    assert first == second
    assert "<svg" in first and "退款" in first
    assert "http" not in first
```

Also test one-document fallback, empty corpus, Chinese tokenization, cluster bounds, and deterministic output.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_text_ml.py -q`

**Step 3: Add runtime dependencies**

Add bounded compatible versions of `jieba`, `numpy`, and `scikit-learn` as required dependencies. Regenerate `uv.lock` with `uv lock`.

**Step 4: Implement the pipeline**

Use TF-IDF, bounded NMF topic discovery, KMeans candidate clustering, silhouette selection for valid candidates, representative passages, outlier scores, and deterministic SVG layout. Persist model/method versions in the result. Never require network access.

**Step 5: Verify GREEN and commit**

Run: `uv run pytest tests/test_text_ml.py -q`

```bash
git add pyproject.toml uv.lock src/data2doc2data/text_ml.py tests/test_text_ml.py
git commit -m "feat: add local text topics clustering and word cloud"
```

### Task 6: Optional local semantic adapter and fallback

**Files:**
- Modify: `pyproject.toml`
- Create: `src/data2doc2data/semantic_text.py`
- Create: `tests/test_semantic_text.py`

**Step 1: Write failing adapter/fallback tests**

```python
def test_uses_local_embedding_adapter_without_network(tmp_path):
    adapter = FakeLocalEmbeddingAdapter([[1.0, 0.0], [0.9, 0.1]])
    result = semantic_cluster(passages(), adapter=adapter)
    assert result.method == "local_embeddings"


def test_falls_back_to_tfidf_when_model_is_unavailable():
    result = semantic_cluster(passages(), adapter=UnavailableAdapter())
    assert result.method == "tfidf_fallback"
    assert result.diagnostics[0]["code"] == "embedding_model_unavailable"
```

**Step 2: Verify RED**

Run: `uv run pytest tests/test_semantic_text.py -q`

**Step 3: Implement a protocol-based adapter**

Do not download models. Accept only an explicitly configured local model path. Put Sentence Transformers in an optional `semantic` extra. Fall back to the Task 5 pipeline on import, configuration, or model-load failure.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_semantic_text.py -q`

```bash
git add pyproject.toml src/data2doc2data/semantic_text.py tests/test_semantic_text.py
git commit -m "feat: add optional local semantic text adapter"
```

### Task 7: Structured claims and cross-modal analytical tools

**Files:**
- Modify: `src/data2doc2data/text_dashboard.py`
- Create: `src/data2doc2data/cross_modal.py`
- Create: `tests/test_cross_modal.py`
- Modify: `tests/test_text_dashboard.py`

**Step 1: Write failing extraction and alignment tests**

```python
def test_extracts_claim_from_ordinary_prose_with_metric_direction_and_citation():
    dashboard = build_text_dashboard(corpus_with("五月直播渠道退款明显上升。"))
    claim = dashboard.claims[0]
    assert claim.metric_refs == ("refund_rate",)
    assert claim.direction == "up"
    assert claim.time_refs == ("五月",)


def test_topic_metric_alignment_uses_shared_periods_and_cites_artifacts():
    artifact = compare_topics_with_metrics(topic_trend(), metric_trend())
    assert artifact.observations["overlap"] >= 8
    assert artifact.source_refs == ("topic-artifact", "metric-artifact")
```

Test alias normalization, negation, ambiguous prose, missing periods, and required non-causality limits.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_cross_modal.py tests/test_text_dashboard.py -q`

**Step 3: Implement structured extraction and cross-modal tools**

Add metric refs, direction, time refs, entities, and citations to claims. Implement `compare_topics_with_metrics`, `test_text_metric_lag`, and `find_explanatory_segments` over artifacts. Rank candidates but label them hypotheses, not causes.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_cross_modal.py tests/test_text_dashboard.py -q`

```bash
git add src/data2doc2data/text_dashboard.py src/data2doc2data/cross_modal.py tests/test_cross_modal.py tests/test_text_dashboard.py
git commit -m "feat: connect text themes to metric evidence"
```

### Task 8: Register deep-analysis tools and compact artifact envelopes

**Files:**
- Create: `src/data2doc2data/artifacts.py`
- Modify: `src/data2doc2data/flow_tools.py`
- Modify: `src/data2doc2data/flow_engine.py`
- Modify: `tests/test_flow_tools.py`
- Modify: `tests/test_flow_engine.py`

**Step 1: Write failing registry, privacy, and provenance tests**

```python
def test_deep_tool_returns_artifact_ref_and_bounded_agent_projection():
    result = tools.detect_anomalies(path, "snapshot-1", metric="gmv")
    assert result.artifact_refs
    envelope = result.agent_projection()
    assert len(json.dumps(envelope, ensure_ascii=False)) <= 8192
    assert "rows" not in json.dumps(envelope)
    assert str(path) not in json.dumps(envelope)


def test_connected_registry_accepts_diagnostics_and_rejects_arbitrary_tool():
    assert "detect_anomalies" in ConnectedFlowRunner.REGISTERED_TOOLS
    with pytest.raises(FlowPlanError):
        validate_flow_plan(plan(tool="python"), ConnectedFlowRunner.REGISTERED_TOOLS)
```

**Step 2: Verify RED**

Run: `uv run pytest tests/test_flow_tools.py tests/test_flow_engine.py -q`

**Step 3: Implement immutable artifact storage and tool adapters**

Register all approved diagnostic, text-ML, and cross-modal tools. Validate metric/dimension names, numeric bounds, seeds, and artifact references. Save full artifacts locally; expose only compact projections to planners.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_flow_tools.py tests/test_flow_engine.py -q`

```bash
git add src/data2doc2data/artifacts.py src/data2doc2data/flow_tools.py src/data2doc2data/flow_engine.py tests/test_flow_tools.py tests/test_flow_engine.py
git commit -m "feat: expose bounded deep-analysis artifacts"
```

### Task 9: Analysis-cycle and round-decision contracts

**Files:**
- Create: `src/data2doc2data/analysis_cycle.py`
- Create: `tests/test_analysis_cycle.py`
- Modify: `src/data2doc2data/run_events.py`
- Modify: `tests/test_run_events.py`

**Step 1: Write failing contract tests**

```python
def test_round_decision_requires_prior_artifact_for_revision():
    with pytest.raises(CyclePlanError):
        validate_round_decision(revision_without_prior_ref(), allowed_tools())


def test_cycle_stops_after_three_rounds():
    cycle = AnalysisCycle.start("cycle-1", max_rounds=3)
    cycle = cycle.complete_round(round_result(1)).complete_round(round_result(2)).complete_round(round_result(3))
    assert cycle.can_continue is False
```

Test `continue`/`finish`, stop criteria, non-redundant revision, argument bounds, and event kinds.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_analysis_cycle.py tests/test_run_events.py -q`

**Step 3: Implement contracts and event vocabulary**

Create immutable `AnalysisCycle`, `AnalysisRound`, `RoundDecision`, `EvidenceGap`, and validation functions. Add cycle/round/artifact/planner events while preserving contract version 1 compatibility for old runs.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_analysis_cycle.py tests/test_run_events.py -q`

```bash
git add src/data2doc2data/analysis_cycle.py src/data2doc2data/run_events.py tests/test_analysis_cycle.py tests/test_run_events.py
git commit -m "feat: define persisted three-round analysis cycles"
```

### Task 10: Persisted Demo policy and checkpoint recovery

**Files:**
- Create: `src/data2doc2data/cycle_runner.py`
- Create: `tests/test_cycle_runner.py`
- Modify: `src/data2doc2data/workspace_store.py`
- Modify: `tests/test_workspace_store.py`
- Modify: `src/data2doc2data/flow_engine.py`

**Step 1: Write failing persistence and recovery tests**

```python
def test_demo_cycle_revises_using_real_first_round_artifact(store, case):
    result = DemoCycleRunner(store).run(case.task, case.inputs)
    assert len(result.cycle.rounds) >= 2
    assert result.cycle.rounds[1].decision.prior_artifact_refs
    assert set(result.cycle.rounds[1].decision.prior_artifact_refs) <= set(result.cycle.rounds[0].artifact_refs)


def test_resume_continues_from_checkpoint_without_reexecuting_completed_tool(store, case):
    checkpoint = interrupted_after_first_artifact(store, case)
    result = DemoCycleRunner(store).resume(checkpoint.cycle_id)
    assert execution_count(store, checkpoint.first_tool_id) == 1
    assert result.cycle.status == "completed"
```

Test tool failure, interruption, third-round limit, no-valid-revision, and partial report states.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_cycle_runner.py tests/test_workspace_store.py -q`

**Step 3: Add cycle tables and deterministic policy**

Persist cycles, rounds, decisions, and artifact links in SQLite with idempotent writes and migration tests. Implement the deterministic policy to choose diagnostics based on schemas and prior artifact gaps; it must not use pre-authored event sequences.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_cycle_runner.py tests/test_workspace_store.py tests/test_flow_engine.py -q`

```bash
git add src/data2doc2data/cycle_runner.py src/data2doc2data/workspace_store.py src/data2doc2data/flow_engine.py tests/test_cycle_runner.py tests/test_workspace_store.py
git commit -m "feat: persist and resume model-free analysis cycles"
```

### Task 11: Backend connected planner with bounded provider envelopes

**Files:**
- Create: `src/data2doc2data/cycle_planner.py`
- Create: `tests/test_cycle_planner.py`
- Modify: `src/data2doc2data/workbench_api.py`
- Modify: `src/data2doc2data/server.py`
- Modify: `tests/test_workbench_api.py`
- Modify: `tests/test_server.py`
- Delete: `web/src/features/tasks/agent-flow-planner.ts`
- Delete: `web/src/features/tasks/agent-flow-planner.test.ts`
- Modify: `web/src/features/tasks/TaskShell.tsx`

**Step 1: Write failing planner/privacy tests**

```python
def test_connected_planner_receives_only_bounded_derived_envelope(fake_gateway, cycle):
    decision = ConnectedCyclePlanner(fake_gateway).decide(cycle)
    sent = fake_gateway.messages[-1]
    assert decision.action == "continue"
    assert "raw rows" not in sent
    assert "/Users/" not in sent
    assert len(sent.encode("utf-8")) <= MAX_PLANNER_PROMPT_BYTES


def test_disconnect_checkpoints_and_resume_reuses_provider_session(fake_gateway, store):
    runner = connected_runner_that_disconnects_once(fake_gateway, store)
    waiting = runner.run()
    assert waiting.cycle.status == "waiting_for_planner"
    completed = runner.resume()
    assert completed.cycle.status == "completed"
```

**Step 2: Verify RED**

Run: `uv run pytest tests/test_cycle_planner.py tests/test_workbench_api.py tests/test_server.py -q`

**Step 3: Implement backend planner and API migration**

Build and parse the round-decision JSON in Python. Use read-only provider sessions, reject approvals during planning, persist provider resume IDs, bound waiting/timeout states, and permit deterministic fallback only when policy allows. Change `POST /api/tasks/{id}/runs` so connected tasks no longer require a browser-authored `flow_plan`. Remove the frontend planner and let `TaskShell` display backend planner events.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_cycle_planner.py tests/test_workbench_api.py tests/test_server.py tests/test_web_agent_contract.py -q`

Run: `cd web && npm test -- --run src/features/tasks`

```bash
git add src/data2doc2data/cycle_planner.py src/data2doc2data/workbench_api.py src/data2doc2data/server.py tests/test_cycle_planner.py tests/test_workbench_api.py tests/test_server.py web/src/features/tasks
git commit -m "feat: move connected agent loop to the backend"
```

### Task 12: Artifact-backed evidence graph, dashboard blocks, and report

**Files:**
- Modify: `src/data2doc2data/evidence_graph.py`
- Modify: `src/data2doc2data/dashboard.py`
- Modify: `src/data2doc2data/reporting.py`
- Modify: `tests/test_evidence_graph.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_reporting.py`
- Modify: `src/data2doc2data/mcp_server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `src/data2doc2data/cli.py`
- Modify: `tests/test_cli.py`

**Step 1: Write failing parity tests**

```python
def test_artifacts_become_evidence_nodes_and_dashboard_blocks(cycle_result):
    assert node(cycle_result.graph, cycle_result.anomaly_artifact_id).kind == "analytical_artifact"
    assert block(cycle_result.dashboard, "anomalies").provenance.artifact_ref == cycle_result.anomaly_artifact_id


def test_offline_report_contains_methods_limits_and_no_external_assets(cycle_result):
    report = build_html_report_from_cycle(cycle_result)
    assert "MAD" in report.html
    assert "不代表因果" in report.html
    assert "https://" not in report.html
```

Add CLI/MCP tests that list artifacts, run model-free cycles, and generate the same report contract.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_evidence_graph.py tests/test_dashboard.py tests/test_reporting.py tests/test_mcp_server.py tests/test_cli.py -q`

**Step 3: Implement shared artifact consumers**

Add analytical artifact and text-theme node kinds. Build anomaly, change-point, contribution, relationship, group, word-cloud, topic, cluster, evolution, and cross-modal blocks from artifacts. Embed safe SVG and compact data in the offline report. Expose cycle/artifact/report operations through CLI and MCP without duplicating analysis logic.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_evidence_graph.py tests/test_dashboard.py tests/test_reporting.py tests/test_mcp_server.py tests/test_cli.py -q`

```bash
git add src/data2doc2data/evidence_graph.py src/data2doc2data/dashboard.py src/data2doc2data/reporting.py src/data2doc2data/mcp_server.py src/data2doc2data/cli.py tests/test_evidence_graph.py tests/test_dashboard.py tests/test_reporting.py tests/test_mcp_server.py tests/test_cli.py
git commit -m "feat: publish analytical artifacts across dashboard report and tools"
```

### Task 13: Rich bundled cases with known numeric and text-ML truth

**Files:**
- Modify: `src/data2doc2data/sample/cases/saas-growth-retention/metrics.csv`
- Modify: `src/data2doc2data/sample/cases/saas-growth-retention/documents/*.md`
- Modify: `src/data2doc2data/sample/cases/saas-growth-retention/expected.json`
- Modify: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/metrics.csv`
- Modify: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/documents/*.md`
- Modify: `src/data2doc2data/sample/cases/retail-promotion-fulfillment/expected.json`
- Modify: `tests/test_flagship_cases.py`

**Step 1: Write failing expected-truth tests**

Assert known anomaly dates, change points, top contribution dimensions, topic keywords, representative citations, cross-modal lag candidates, and round count for both cases.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_flagship_cases.py -q`

**Step 3: Expand the fixtures**

Add region/channel/product dimensions and repeated text evidence over time. Keep each case human-auditable and document the injected ground truth in `expected.json`.

**Step 4: Verify GREEN and commit**

Run: `uv run pytest tests/test_flagship_cases.py -q`

```bash
git add src/data2doc2data/sample/cases tests/test_flagship_cases.py
git commit -m "test: add rich cross-modal flagship cases"
```

### Task 14: Workbench artifact views and real round animation

**Files:**
- Modify: `web/src/contracts/dashboard.ts`
- Modify: `web/src/contracts/run-events.ts`
- Modify: `web/src/features/dashboard/DashboardCanvas.tsx`
- Modify: `web/src/features/dashboard/DashboardCanvas.test.tsx`
- Create: `web/src/features/dashboard/DiagnosticBlocks.tsx`
- Create: `web/src/features/dashboard/DiagnosticBlocks.test.tsx`
- Modify: `web/src/features/documents/TextDashboard.tsx`
- Modify: `web/src/features/documents/TextDashboard.test.tsx`
- Modify: `web/src/features/flow/flow-projection.ts`
- Modify: `web/src/features/flow/flow-projection.test.ts`
- Modify: `web/src/features/flow/AgentFlowCanvas.tsx`
- Modify: `web/src/features/flow/AgentFlowCanvas.test.tsx`
- Modify: `web/src/styles/app.css`

**Step 1: Write failing UI behavior tests**

Test accessible anomaly timeline, contribution view, word cloud, topic cards, cluster view, method/limitation provenance, round grouping, planner waiting/recovery, and evidence links. Assert a second-round node references a first-round artifact.

**Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/dashboard src/features/documents src/features/flow`

**Step 3: Implement the views**

Use ECharts only where it materially clarifies quantitative relationships. Render the SVG word cloud directly, use accessible tables as fallbacks, keep the minimap omitted, and animate persisted events at readable speed. Label the process as an audit trail, not thought disclosure.

**Step 4: Verify GREEN and commit**

Run: `cd web && npm test -- --run src/features/dashboard src/features/documents src/features/flow`

```bash
git add web/src/contracts web/src/features/dashboard web/src/features/documents web/src/features/flow web/src/styles/app.css
git commit -m "feat: visualize diagnostic and text ML artifacts"
```

### Task 15: Recovery, privacy, responsive, and offline end-to-end tests

**Files:**
- Modify: `web/e2e/workbench.spec.ts`
- Modify: `web/e2e/live-assistant.spec.ts`
- Create: `web/e2e/analysis-cycle.spec.ts`
- Modify: `tests/test_public_boundary.py`
- Modify: `tests/test_quality_contract.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `docs/plans/task.md`

**Step 1: Add failing end-to-end scenarios**

Cover:

- a model-free three-round Demo with real artifact references;
- Codex and WorkBuddy connected revisions when available;
- reload during a running local tool;
- provider disconnect and resume;
- planner timeout and deterministic fallback;
- tool failure and partial report;
- interruption at a tool boundary;
- 390px and 1440px layouts;
- exact known diagnostic results from both cases;
- offline HTML with no external requests;
- raw-row/path absence in provider fixtures and logs.

**Step 2: Verify RED**

Run: `uv run pytest tests/test_public_boundary.py tests/test_quality_contract.py tests/test_release_bundle.py -q`

Run: `cd web && npx playwright test e2e/analysis-cycle.spec.ts --workers=1`

**Step 3: Fix only integration gaps exposed by the tests**

Do not loosen numeric, privacy, recovery, or accessibility assertions to make tests pass.

**Step 4: Run the complete verification suite**

Run: `uv run pytest -q`

Run: `uv run coverage run -m pytest && uv run coverage report`

Run: `cd web && npm test -- --run`

Run: `cd web && npm run typecheck`

Run: `cd web && npm run build`

Run: `cd web && npm run e2e`

Expected: all locally runnable tests pass, coverage remains at least 80%, the two real-provider tests skip only when their CLI/auth prerequisites are absent, and the build contains no missing static assets.

**Step 5: Perform browser visual QA**

Inspect both flagship cases at 1440×1024 and 390×844. Save before/after screenshots under `docs/audits/2026-08-24-local-ml-agent-loop/`. Verify there is no document horizontal overflow, no overlapping sticky regions, readable chart labels, useful empty/error states, and understandable round transitions.

**Step 6: Commit**

```bash
git add web/e2e tests/test_public_boundary.py tests/test_quality_contract.py tests/test_release_bundle.py docs/plans/task.md docs/audits/2026-08-24-local-ml-agent-loop
git commit -m "test: verify local ML agent loop end to end"
```
