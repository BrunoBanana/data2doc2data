# Trusted Analysis and Local Agent Gateway Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Build a reproducible local evidence engine and a secure web gateway for locally installed Codex and Tencent WorkBuddy/CodeBuddy.

**Architecture:** Split deterministic analysis into metric, retrieval, hypothesis, and provenance modules. Add a provider-neutral agent gateway behind the existing loopback HTTP server; normalize Codex JSON-RPC and WorkBuddy ACP/HTTP into SSE events consumed by the existing browser UI. Keep evidence validation authoritative and require explicit permission-broker approval for writes, commands, and state-changing tools.

**Tech Stack:** Python 3.10+ standard library, dataclasses, unittest, `http.server`, JSON-RPC, SSE, vanilla HTML/CSS/JavaScript, GitHub Actions.

---

### Task 1: Add CI and development quality gates

**Files:**
- Modify: `pyproject.toml`
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_quality_contract.py`

**Step 1: Write the failing quality-contract test**

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class QualityContractTests(unittest.TestCase):
    def test_ci_runs_the_complete_unittest_suite(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13"]', workflow)
```

**Step 2: Run the test and verify it fails**

Run: `python -m unittest tests.test_quality_contract -v`

Expected: FAIL because `.github/workflows/ci.yml` does not exist.

**Step 3: Add the minimal CI workflow**

```yaml
name: CI
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install -e .
      - run: python -m unittest discover -s tests -v
```

Add optional development dependencies and unittest coverage tooling in `pyproject.toml` without adding runtime dependencies.

**Step 4: Run all tests**

Run: `python -m unittest discover -s tests -v`

Expected: all existing and new tests PASS.

**Step 5: Commit**

```bash
git add pyproject.toml .github/workflows/ci.yml tests/test_quality_contract.py
git commit -m "ci: add Python test matrix"
```

### Task 2: Lock in known correctness regressions

**Files:**
- Modify: `tests/test_analysis.py`
- Modify: `src/data2doc2data/analysis.py`

**Step 1: Add failing tests for zero baselines and non-finite values**

```python
def test_zero_baseline_does_not_report_a_nonzero_current_value_as_flat(self):
    signal = _build_signal(
        "revenue",
        [
            MetricRow(date.fromisoformat("2026-01-01"), "revenue", 0.0),
            MetricRow(date.fromisoformat("2026-02-01"), "revenue", 10.0),
        ],
    )
    self.assertEqual(signal.direction, "up")
    self.assertIsNone(signal.change_percent)

def test_csv_rejects_non_finite_values(self):
    # Build a temporary CSV containing NaN and assert InputValidationError.
```

**Step 2: Add failing adversarial direction tests**

```python
def test_reversed_english_condition_is_not_confirmed(self):
    context = DocumentContext("decision.md", "Retention rises while activation falls.", 4)
    verification = _verify_document_condition(primary_signal, rows, context)
    self.assertNotEqual(verification.status, "confirmed")

def test_reversed_chinese_condition_is_not_confirmed(self):
    context = DocumentContext("decision.md", "激活下降、留存上升。", 8)
    verification = _verify_document_condition(primary_signal, rows, context)
    self.assertNotEqual(verification.status, "confirmed")
```

**Step 3: Run the focused tests**

Run: `python -m unittest tests.test_analysis.AnalysisTests -v`

Expected: new tests FAIL against the current implementation.

**Step 4: Implement minimal safe corrections**

- Reject values for which `math.isfinite(value)` is false.
- Change relative change to `float | None`.
- For a zero baseline, derive direction from absolute change.
- Replace unordered English/Chinese set matching with subject-direction regex patterns that preserve order.

**Step 5: Run analysis and full tests**

Run: `python -m unittest tests.test_analysis -v && python -m unittest discover -s tests -v`

Expected: all tests PASS.

**Step 6: Commit**

```bash
git add src/data2doc2data/analysis.py tests/test_analysis.py
git commit -m "fix: prevent false evidence confirmations"
```

### Task 3: Introduce MetricSpec and a reusable signal engine

**Files:**
- Create: `src/data2doc2data/metrics.py`
- Create: `tests/test_metrics.py`
- Modify: `src/data2doc2data/analysis.py`
- Modify: `src/data2doc2data/__init__.py`

**Step 1: Write failing MetricSpec validation tests**

```python
from data2doc2data.metrics import MetricSpec, SignalEngine


class MetricTests(unittest.TestCase):
    def test_previous_period_mean_records_ranges_and_counts(self):
        spec = MetricSpec(name="retention_rate", aggregation="mean", threshold=1.0)
        signal = SignalEngine().build(spec, rows)
        self.assertEqual(signal.baseline_count, 2)
        self.assertEqual(signal.current_count, 2)
        self.assertEqual(signal.baseline_range.start.isoformat(), "2026-01-01")

    def test_duplicate_dates_are_rejected_by_default(self):
        with self.assertRaisesRegex(InputValidationError, "duplicate"):
            SignalEngine().build(MetricSpec(name="revenue"), duplicate_rows)
```

**Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_metrics -v`

Expected: FAIL because `data2doc2data.metrics` does not exist.

**Step 3: Implement the domain types**

```python
@dataclass(frozen=True)
class MetricSpec:
    name: str
    aliases: tuple[str, ...] = ()
    display_name: str | None = None
    unit: str | None = None
    aggregation: Literal["mean", "sum", "latest", "min", "max"] = "mean"
    comparison: Literal["split_window", "previous_period"] = "split_window"
    threshold: float = 1.0
    minimum_observations: int = 2
    duplicate_policy: Literal["reject", "mean", "sum"] = "reject"
```

Add `DateRange`, the expanded `Signal`, a finite-value guard, aggregation functions, and explicit duplicate-date handling. Keep the default behavior compatible with existing demo results.

**Step 4: Delegate analysis to SignalEngine**

Replace `_build_signal` internals with a compatibility wrapper around `SignalEngine`. Preserve current public fields while adding ranges, counts, absolute change, nullable relative change, and the serialized spec.

**Step 5: Run all tests**

Run: `python -m unittest tests.test_metrics tests.test_analysis tests.test_server -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add src/data2doc2data/metrics.py src/data2doc2data/analysis.py src/data2doc2data/__init__.py tests/test_metrics.py
git commit -m "feat: add configurable metric signal engine"
```

### Task 4: Replace hard-coded verification with structured hypotheses

**Files:**
- Create: `src/data2doc2data/hypotheses.py`
- Create: `tests/test_hypotheses.py`
- Modify: `src/data2doc2data/analysis.py`
- Modify: `tests/test_analysis.py`

**Step 1: Write failing parser tests**

```python
def test_parser_preserves_metric_subjects_and_directions(self):
    hypothesis = parse_controlled_hypothesis("激活率上升，同时留存率下降")
    self.assertEqual(
        [(clause.metric, clause.direction) for clause in hypothesis.clauses],
        [("activation_rate", "up"), ("retention_rate", "down")],
    )

def test_parser_rejects_negated_or_ambiguous_text(self):
    self.assertIsNone(parse_controlled_hypothesis("不能说明激活率上升导致留存率下降"))
```

**Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_hypotheses -v`

Expected: FAIL because the module is missing.

**Step 3: Implement structured hypothesis types**

```python
@dataclass(frozen=True)
class HypothesisClause:
    metric: str
    direction: Literal["up", "down", "flat"]

@dataclass(frozen=True)
class HypothesisSpec:
    clauses: tuple[HypothesisClause, ...]
    time_relation: Literal["same_window"] = "same_window"
    source: Literal["deterministic", "agent_proposed", "user_confirmed"] = "deterministic"
```

Implement controlled Chinese and English parsers that bind each metric to its adjacent direction phrase and reject explicit negation. Add a schema validator for agent-proposed JSON.

**Step 4: Implement generic clause verification**

Build every referenced metric with `SignalEngine`, compare directions, and return clause-level `confirmed`, `contradicted`, or `unavailable`. Derive the overall validation state from all clause results.

**Step 5: Remove the single-purpose activation/retention verifier**

Keep the demo behavior through a parsed built-in hypothesis, not a hard-coded branch in `analysis.py`.

**Step 6: Run tests and commit**

Run: `python -m unittest tests.test_hypotheses tests.test_analysis -v`

Expected: PASS, including reversed and negated statement regressions.

```bash
git add src/data2doc2data/hypotheses.py src/data2doc2data/analysis.py tests/test_hypotheses.py tests/test_analysis.py
git commit -m "feat: verify structured metric hypotheses"
```

### Task 5: Add document indexing and complete provenance

**Files:**
- Create: `src/data2doc2data/retrieval.py`
- Create: `src/data2doc2data/provenance.py`
- Create: `tests/test_retrieval.py`
- Create: `tests/test_provenance.py`
- Modify: `src/data2doc2data/analysis.py`
- Modify: `src/data2doc2data/config.py`

**Step 1: Write failing retrieval tests**

```python
def test_chinese_bigram_ranking_preserves_word_order(self):
    chunks = index_documents([supporting_path, reversed_path])
    ranked = search_chunks("激活上升 留存下降", chunks)
    self.assertEqual(ranked[0].path, supporting_path)

def test_chunk_records_line_range_and_sha256(self):
    chunk = index_documents([document_path])[0]
    self.assertEqual(chunk.start_line, 1)
    self.assertGreaterEqual(chunk.end_line, chunk.start_line)
    self.assertRegex(chunk.sha256, r"^[0-9a-f]{64}$")
```

**Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_retrieval tests.test_provenance -v`

Expected: FAIL because the modules do not exist.

**Step 3: Implement deterministic indexing and search**

Create line-aware paragraph chunks. Use English words plus Chinese character bigrams/trigrams, BM25-style term scoring, deterministic tie-breaking by path and line, and a minimum normalized relevance threshold.

**Step 4: Implement provenance types**

```python
@dataclass(frozen=True)
class SourceRef:
    path: str
    sha256: str
    rows: tuple[int, ...] = ()
    start_line: int | None = None
    end_line: int | None = None

@dataclass(frozen=True)
class AnalysisProvenance:
    analysis_id: str
    engine_version: str
    sources: tuple[SourceRef, ...]
    parameters: dict[str, object]
```

Use a deterministic content-derived analysis ID for identical inputs and parameters. Record CSV row numbers while reading metrics.

**Step 5: Add cache storage**

Store only the local document index under the profile configuration directory. Invalidate entries by path, size, modification time, and SHA-256. Write atomically with mode `0600`.

**Step 6: Integrate and verify**

Run: `python -m unittest tests.test_retrieval tests.test_provenance tests.test_analysis -v`

Expected: PASS; InsightResult contains exact source references and engine version.

**Step 7: Commit**

```bash
git add src/data2doc2data/retrieval.py src/data2doc2data/provenance.py src/data2doc2data/analysis.py src/data2doc2data/config.py tests/test_retrieval.py tests/test_provenance.py
git commit -m "feat: add indexed retrieval and reproducible provenance"
```

### Task 6: Define the provider-neutral agent gateway

**Files:**
- Create: `src/data2doc2data/agents/__init__.py`
- Create: `src/data2doc2data/agents/base.py`
- Create: `src/data2doc2data/agents/gateway.py`
- Create: `tests/test_agent_gateway.py`

**Step 1: Write failing provider contract tests**

```python
class FakeProvider:
    name = "fake"
    def detect(self):
        return ProviderStatus(available=True, connected=False, version="1.0")
    def stream_turn(self, session, message):
        yield AgentEvent(kind="message.delta", payload={"text": "hello"})
        yield AgentEvent(kind="turn.completed", payload={})

def test_gateway_normalizes_provider_events(self):
    events = list(AgentGateway({"fake": FakeProvider()}).send("fake", session, "hi"))
    self.assertEqual([event.kind for event in events], ["message.delta", "turn.completed"])
```

**Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_agent_gateway -v`

Expected: FAIL because the agent package is missing.

**Step 3: Implement protocol-neutral types**

Define `ProviderStatus`, `AgentSession`, `AgentEvent`, `ApprovalRequest`, `AgentProvider` protocol, and typed gateway errors: `NotInstalled`, `NotAuthenticated`, `IncompatibleVersion`, `ProviderUnavailable`, `ProviderTimeout`, and `InvalidProviderPayload`.

**Step 4: Implement gateway lifecycle and cancellation**

Add provider detection, connection, session creation/resumption, event normalization, turn interruption, and cleanup. Unknown event fields are ignored; missing required fields reject the event.

**Step 5: Run and commit**

Run: `python -m unittest tests.test_agent_gateway -v`

Expected: PASS.

```bash
git add src/data2doc2data/agents tests/test_agent_gateway.py
git commit -m "feat: add provider-neutral agent gateway"
```

### Task 7: Add permission broker and local audit store

**Files:**
- Create: `src/data2doc2data/permissions.py`
- Create: `src/data2doc2data/sessions.py`
- Create: `tests/test_permissions.py`
- Create: `tests/test_sessions.py`

**Step 1: Write failing permission tests**

```python
def test_collaborative_mode_blocks_command_until_approved(self):
    broker = PermissionBroker(mode="collaborative", roots=(workspace,))
    decision = broker.evaluate(command_request)
    self.assertEqual(decision.status, "pending")

def test_target_outside_workspace_is_rejected_even_after_approval(self):
    broker = PermissionBroker(mode="trusted_session", roots=(workspace,))
    self.assertEqual(broker.evaluate(outside_write).status, "rejected")
```

**Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_permissions tests.test_sessions -v`

Expected: FAIL because the modules do not exist.

**Step 3: Implement permission decisions**

Support `read_only`, `collaborative`, and `trusted_session`. Resolve paths before comparison, reject traversal and out-of-root targets, expire approvals, and scope temporary grants to provider, session, operation kind, command prefix, and root.

**Step 4: Implement redacted audit persistence**

Write append-only JSON Lines with mode `0600`. Store timestamps, provider, session, operation summary, decision, exit status, and target paths. Redact values matching credential patterns and never store inherited environment variables.

**Step 5: Run and commit**

Run: `python -m unittest tests.test_permissions tests.test_sessions -v`

Expected: PASS.

```bash
git add src/data2doc2data/permissions.py src/data2doc2data/sessions.py tests/test_permissions.py tests/test_sessions.py
git commit -m "feat: add session-scoped permissions and audit log"
```

### Task 8: Implement the Codex App Server adapter

**Files:**
- Create: `src/data2doc2data/agents/codex.py`
- Create: `tests/test_codex_adapter.py`
- Create: `tests/fixtures/codex_app_server/turn.jsonl`

**Step 1: Write a failing fake-server contract test**

The fake child process must accept `initialize`, `thread/start`, and `turn/start`, then emit `item/agentMessage/delta`, approval, and `turn/completed` messages. Assert that the adapter converts each message into the normalized event model.

**Step 2: Verify the test fails**

Run: `python -m unittest tests.test_codex_adapter -v`

Expected: FAIL because `CodexProvider` is missing.

**Step 3: Implement safe detection and startup**

Use `shutil.which("codex")`, run `codex --version` with a short timeout, and start `codex app-server --stdio` only after an explicit connection request. Set the working directory to the approved workspace and never pass bypass flags.

**Step 4: Implement JSON-RPC request routing**

Maintain monotonically increasing request IDs, a pending-response table, one reader thread, protocol initialization, session mapping, event normalization, approval responses, interruption, and process cleanup.

**Step 5: Test crash and timeout handling**

Assert that process exit produces `provider.error`, pending approvals expire, and subsequent deterministic analysis remains available.

**Step 6: Run and commit**

Run: `python -m unittest tests.test_codex_adapter tests.test_agent_gateway -v`

Expected: PASS without requiring a real Codex login.

```bash
git add src/data2doc2data/agents/codex.py tests/test_codex_adapter.py tests/fixtures/codex_app_server/turn.jsonl
git commit -m "feat: connect local Codex app server"
```

### Task 9: Implement the WorkBuddy ACP/HTTP adapter

**Files:**
- Create: `src/data2doc2data/agents/workbuddy.py`
- Create: `tests/test_workbuddy_adapter.py`
- Create: `tests/fixtures/workbuddy/acp-stream.txt`

**Step 1: Write a failing local fake-HTTP test**

Start a test `ThreadingHTTPServer` exposing `/api/v1/health` and `/api/v1/acp`. Return JSON-RPC events through SSE and assert normalized message, tool, approval, and completion events.

**Step 2: Verify the test fails**

Run: `python -m unittest tests.test_workbuddy_adapter -v`

Expected: FAIL because `WorkBuddyProvider` is missing.

**Step 3: Implement detection and connection**

Detect `codebuddy`, validate `codebuddy --version`, and connect only to configured loopback endpoints. On explicit startup, run `codebuddy --serve --port <free-port> --session-id <uuid>` with approved permission mode and workspace.

**Step 4: Implement public API and ACP handling**

Use only `/api/v1/*`. Parse SSE framing incrementally, validate JSON-RPC envelopes, map sessions, send turns, route approvals, interrupt runs, and close the owned process on shutdown.

**Step 5: Test invalid endpoints and CORS-independent backend use**

Reject non-loopback endpoint configuration. Confirm provider errors are normalized and do not leak response bodies containing secrets.

**Step 6: Run and commit**

Run: `python -m unittest tests.test_workbuddy_adapter tests.test_agent_gateway -v`

Expected: PASS without requiring a real WorkBuddy login.

```bash
git add src/data2doc2data/agents/workbuddy.py tests/test_workbuddy_adapter.py tests/fixtures/workbuddy/acp-stream.txt
git commit -m "feat: connect local WorkBuddy ACP gateway"
```

### Task 10: Expose secure session and SSE APIs

**Files:**
- Modify: `src/data2doc2data/server.py`
- Modify: `src/data2doc2data/cli.py`
- Modify: `tests/test_server.py`
- Create: `tests/test_agent_server.py`

**Step 1: Write failing HTTP API tests**

Cover `GET /api/agents`, session creation, message submission, SSE events, approval decisions, interruption, invalid session IDs, expired approvals, request limits, and provider-unavailable fallback.

**Step 2: Add failing CSRF tests**

Assert that state-changing agent endpoints reject missing/incorrect CSRF tokens even when Host and Origin are valid. Assert the session cookie is `HttpOnly; SameSite=Strict`.

**Step 3: Verify failures**

Run: `python -m unittest tests.test_agent_server -v`

Expected: FAIL because routes are absent.

**Step 4: Implement agent API routing**

Extract route matching from the handler, inject `AgentGateway`, `PermissionBroker`, and session store into the server, create CSRF/session tokens with `secrets.token_urlsafe`, and add bounded in-memory SSE queues.

**Step 5: Preserve deterministic availability**

Ensure `/api/analyze` never requires an agent. When no provider is available, `/api/agents` returns actionable status and analysis continues normally.

**Step 6: Run and commit**

Run: `python -m unittest tests.test_server tests.test_agent_server -v`

Expected: PASS.

```bash
git add src/data2doc2data/server.py src/data2doc2data/cli.py tests/test_server.py tests/test_agent_server.py
git commit -m "feat: expose secure local agent session API"
```

### Task 11: Build the web conversation and approval experience

**Files:**
- Modify: `src/data2doc2data/static/index.html`
- Modify: `src/data2doc2data/static/app.js`
- Modify: `src/data2doc2data/static/app.css`
- Modify: `tests/test_static_assets.py`
- Create: `tests/test_web_agent_contract.py`

**Step 1: Write failing static contract tests**

Assert accessible provider selection, permission mode, connect button, conversation log, evidence panel, operation queue, approval/reject buttons, interrupt button, and live regions exist. Assert scripts never use `innerHTML` for provider content.

**Step 2: Verify failures**

Run: `python -m unittest tests.test_static_assets tests.test_web_agent_contract -v`

Expected: FAIL because agent controls are absent.

**Step 3: Add provider and session UI**

Render detected status, version, authentication errors, connect action, selected provider, permission mode, and current session. Keep deterministic analysis as the first-class evidence panel.

**Step 4: Add streaming and operation cards**

Use `EventSource` for normalized events. Append messages with `textContent`, render diffs as plain text, show exact command/tool/paths on approval cards, and disable stale or completed approvals.

**Step 5: Add error and fallback states**

Handle agent unavailable, disconnected, timed out, interrupted, approval expired, and incompatible-version states without clearing existing evidence.

**Step 6: Run and commit**

Run: `python -m unittest tests.test_static_assets tests.test_web_agent_contract tests.test_agent_server -v`

Expected: PASS.

```bash
git add src/data2doc2data/static tests/test_static_assets.py tests/test_web_agent_contract.py
git commit -m "feat: add local agent workspace to web UI"
```

### Task 12: Update bundle, documentation, and release evidence

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `CHANGELOG.md`
- Modify: `references/connector-guide.md`
- Modify: `scripts/build_skill_bundle.py`
- Modify: `tests/test_release_bundle.py`
- Modify: `tests/test_public_metadata.py`
- Modify: `pyproject.toml`

**Step 1: Write failing release-boundary tests**

Assert that all new runtime modules are included in the explicit public allowlist, test fixtures/audit logs are excluded, documentation accurately describes agent availability and permission boundaries, and versions agree across package, changelog, and Skill metadata.

**Step 2: Verify failures**

Run: `python -m unittest tests.test_release_bundle tests.test_public_metadata -v`

Expected: FAIL until the new modules and metadata are added.

**Step 3: Update user documentation**

Document deterministic-only use, Codex detection/connection, WorkBuddy `--serve` compatibility, permission modes, approval behavior, local persistence, troubleshooting, and the fact that agent-generated explanations are not evidence validation.

**Step 4: Update release packaging and metadata**

Add new runtime files to `PUBLIC_RESOURCE_FILES`, preserve the explicit allowlist and sensitive-data scan, select a version according to compatibility impact, and add a changelog entry.

**Step 5: Run the complete verification suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS.

Run: `python scripts/build_skill_bundle.py /private/tmp/data2doc2data-release.zip`

Expected: bundle builds successfully and contains no audit, cache, test, or credential files.

**Step 6: Commit**

```bash
git add README.md SKILL.md CHANGELOG.md references/connector-guide.md scripts/build_skill_bundle.py tests/test_release_bundle.py tests/test_public_metadata.py pyproject.toml
git commit -m "docs: publish trusted analysis and local agent workflow"
```

### Task 13: Final regression and security verification

**Files:**
- Modify only files required to correct failures found by this task.

**Step 1: Run the full suite twice**

Run: `python -m unittest discover -s tests -v && python -m unittest discover -s tests -v`

Expected: both runs PASS with no order dependency or leaked child processes.

**Step 2: Verify process and network boundaries**

Run integration tests that assert every HTTP listener binds to `127.0.0.1`, every provider endpoint is loopback, child processes terminate, and pending approvals cannot survive a session restart.

**Step 3: Verify public-bundle privacy**

Run: `python scripts/build_skill_bundle.py /private/tmp/data2doc2data-final.zip`

Expected: PASS; archive inspection finds no `.env`, logs, sessions, caches, user CSVs, or unapproved files.

**Step 4: Review the complete branch diff**

Run: `git diff --check && git status --short && git log --oneline --decorate -15`

Expected: no whitespace errors, no unintended untracked files, and one focused commit per task.

**Step 5: Commit verification-only fixes if needed**

```bash
git add <exact corrected files>
git commit -m "fix: close final integration regressions"
```

Plan complete and saved to `docs/plans/2026-08-16-trusted-analysis-agent-gateway.md`.

Next step: run `.agent/workflows/execute-plan.md` to execute this plan task-by-task in single-flow mode.
