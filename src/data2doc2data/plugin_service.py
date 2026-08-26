"""Task-scoped, privacy-preserving business-analysis workflows for MCP hosts."""

from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
from http import HTTPStatus
import io
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .analysis import InputValidationError, analyze, read_metrics_source
from .analysis_cycle import AnalysisCycle
from .artifacts import ArtifactStore
from .config import Profile, ProfileStore
from .cycle_runner import DemoCycleRunner
from .data_profile import profile_standard_csv
from .flow_tools import DEEP_ANALYSIS_TOOLS, LocalAnalysisTools
from .hypotheses import verify_hypothesis
from .metrics import SignalEngine
from .rules import RuleSet, load_ruleset, parse_ruleset
from .source_resolver import ResolvedDataset, ResolvedSources, SourceResolver
from .workbench_api import WorkbenchApiError, WorkbenchService
from .workspace import AnalysisTask, SnapshotRef
from .workspace_store import WorkspaceStore, WorkspaceStoreError


MCP_OWNER = "mcp-host"
MAX_METRIC_FINDINGS = 50
MAX_DIAGNOSTIC_STEPS = 100
REQUIRED_DATA_FIELDS = frozenset({"date", "metric", "value"})


class PluginService:
    """Give a host agent granular tools without making it manage global profiles."""

    def __init__(self, profile_store: ProfileStore) -> None:
        self.profile_store = profile_store
        self.workspace = WorkspaceStore(profile_store.workspace_database_path)
        self.workbench = WorkbenchService(self.workspace)
        self.artifacts = ArtifactStore(self.workspace.path.parent / "artifacts")

    def inspect_sources(self, paths: Sequence[str]) -> dict[str, object]:
        approved = self._requested_paths(paths)
        result = LocalAnalysisTools(self._source_roots(approved)).inspect_sources(approved)
        return dict(result.agent_projection()["summary"])

    def create_analysis_task(
        self,
        question: str,
        paths: Sequence[str],
        *,
        title: str | None = None,
        rules_path: str | None = None,
    ) -> dict[str, object]:
        if not question.strip():
            raise InputValidationError("question must be a non-empty string")
        approved = self._requested_paths(paths)
        resolved = SourceResolver(self._source_roots(approved)).resolve(approved)
        usable = tuple(dataset for dataset in resolved.datasets if REQUIRED_DATA_FIELDS <= set(dataset.fields))
        if not usable:
            raise InputValidationError("materials must contain a CSV or embedded table with date, metric, value columns")

        flagship = self._requested_flagship(approved)
        case_title = self.workbench.flagship_cases.package(flagship).case.title if flagship is not None else None
        display_title = title or case_title or self._default_title(question, approved)
        created = self.workbench.create_task(
            MCP_OWNER,
            {"title": display_title[:200], "goal": question, "analysis_mode": "demo"},
        )
        task_id = str(created["task"]["task_id"])
        dataset_path = self._dataset_path(task_id, usable, approved)
        dataset_digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
        path_digest = hashlib.sha256(str(dataset_path).encode("utf-8")).hexdigest()[:8]
        dataset_ref = SnapshotRef("dataset", f"dataset-{dataset_digest[:16]}-{path_digest}", dataset_digest)
        self.workspace.register_snapshot(dataset_ref, dataset_path)
        self.workbench.attach_assets(MCP_OWNER, task_id, {"snapshot_refs": [dataset_ref.to_dict()]})
        document_paths = self._document_paths(task_id, resolved, approved)
        if document_paths:
            self.workbench.import_documents(MCP_OWNER, task_id, {"paths": [str(path) for path in document_paths]})
        selected_rules = self._discover_rules(approved)

        if rules_path is not None:
            explicit = Path(rules_path).expanduser().resolve()
            load_ruleset(explicit)
            selected_rules = str(explicit)
        session = {"rules_path": selected_rules, "diagnostic_steps": []}
        self.workspace.save_task_artifact(task_id, "plugin_session", session)
        task = self._owned_task(task_id)
        return {
            "task_id": task.task_id,
            "title": task.title,
            "question": task.goal,
            "source_summary": self.source_summary(task),
            "snapshot_refs": [ref.to_dict() for ref in task.snapshot_refs],
            "diagnostics": [
                {"name": diagnostic.name, "message": diagnostic.message}
                for diagnostic in resolved.diagnostics[:20]
            ],
        }

    def source_summary(self, task: AnalysisTask) -> dict[str, object]:
        data_path, documents = self.workbench._execution_inputs(task)
        dataset = next(ref for ref in reversed(task.snapshot_refs) if ref.kind == "dataset")
        profile = profile_standard_csv(data_path, dataset.snapshot_id)
        return {
            "record_count": profile.row_count,
            "metric_count": len(profile.metrics),
            "metrics": list(profile.metrics[:MAX_METRIC_FINDINGS]),
            "document_count": len(documents),
            "date_range": list(profile.date_range),
            "modalities": ["data", *(["text"] if documents else [])],
        }

    def analyze_task_metric(self, task_id: str, question: str, metric: str | None = None) -> dict[str, object]:
        task = self._owned_task(task_id)
        data_path, documents = self.workbench._execution_inputs(task)
        ruleset = self._task_ruleset(task_id)
        if documents:
            profile = Profile("local", str(data_path), str(self._knowledge_root(task_id, documents)))
            result = analyze(
                question,
                profile,
                metric,
                self.workspace.path.parent / "plugin-sources" / task_id / "document-index.json",
                ruleset,
            )
            payload = self._compact_insight(result.to_dict())
        else:
            if not metric:
                raise InputValidationError("metric must be specified when no documents are available")
            rows, digest = read_metrics_source(data_path)
            signal = SignalEngine().build(ruleset.spec_for(metric) if ruleset else _default_metric_spec(metric), rows)
            payload = {
                "question": question,
                "signal": _json_safe(asdict(signal)),
                "context": {"source": "", "excerpt": "", "relevance": 0},
                "validation": {"status": "insufficient", "summary": "未提供文本材料；这里只验证数据趋势。"},
                "verification": {"status": "unavailable", "summary": "缺少可交叉验证的文本主张。"},
                "evidence": [f"指标来源：{data_path.name}"],
                "provenance": {
                    "analysis_id": hashlib.sha256(f"{digest}:{metric}:{question}".encode("utf-8")).hexdigest(),
                    "sources": [{"name": data_path.name, "sha256": digest, "row_count": len(rows)}],
                },
                "limitation": "数据趋势不等同于因果结论。",
            }
        payload["task_id"] = task.task_id
        return payload

    def evaluate_task_rules(self, task_id: str) -> dict[str, object]:
        task = self._owned_task(task_id)
        data_path, _ = self.workbench._execution_inputs(task)
        ruleset = self._task_ruleset(task_id)
        if ruleset is None:
            return {
                "task_id": task_id,
                "rule_count": 0,
                "confirmed_count": 0,
                "contradicted_count": 0,
                "unavailable_count": 0,
                "results": [],
                "limitation": "未提供声明式业务规则，因此不能声称业务假设已被验证。",
            }
        rows, _ = read_metrics_source(data_path)
        specs = {name: definition.to_spec() for name, definition in ruleset.metrics.items()}
        results = []
        for rule in ruleset.rules:
            verification = verify_hypothesis(rule.hypothesis(), rows, specs)
            results.append(
                {
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "description": rule.description,
                    "status": verification.status,
                    "summary": verification.summary,
                    "clauses": [
                        {
                            "metric": clause.metric,
                            "expected_direction": clause.expected_direction,
                            "observed_direction": clause.observed_direction,
                            "status": clause.status,
                        }
                        for clause in verification.clauses
                    ],
                }
            )
        return {
            "task_id": task_id,
            "rule_count": len(results),
            "confirmed_count": sum(result["status"] == "confirmed" for result in results),
            "contradicted_count": sum(result["status"] == "contradicted" for result in results),
            "unavailable_count": sum(result["status"] == "unavailable" for result in results),
            "results": results,
        }

    def run_diagnostic_step(self, task_id: str, tool: str, arguments: Mapping[str, object]) -> dict[str, object]:
        if tool not in DEEP_ANALYSIS_TOOLS and tool not in {"profile_data", "query_data", "extract_claims", "align_evidence", "test_hypothesis"}:
            raise InputValidationError(f"unsupported diagnostic tool: {tool}")
        task = self._owned_task(task_id)
        data_path, documents = self.workbench._execution_inputs(task)
        dataset = next(ref for ref in reversed(task.snapshot_refs) if ref.kind == "dataset")
        roots = [data_path.parent, *(document.parent for document in documents)]
        model_path = arguments.get("model_path")
        if tool == "semantic_cluster" and isinstance(model_path, str):
            roots.append(Path(model_path).expanduser().resolve().parent)
        tools = LocalAnalysisTools(roots, artifact_store=self.artifacts)
        corpus_id = f"corpus-{task_id}"
        options = dict(arguments)
        if tool == "profile_data":
            result = tools.profile_data(data_path, dataset.snapshot_id)
        elif tool == "query_data":
            result = tools.query_data(data_path, dataset.snapshot_id, str(options["metric"]))
        elif tool == "extract_claims":
            result = tools.extract_claims(documents, corpus_id)
        elif tool == "align_evidence":
            result = tools.align_evidence(data_path, dataset.snapshot_id, documents, corpus_id)
        elif tool == "test_hypothesis":
            result = tools.test_hypothesis(data_path, dataset.snapshot_id, options.get("hypothesis", options))
        elif tool in {"analyze_text", "semantic_cluster"}:
            result = getattr(tools, tool)(documents, corpus_id, **options)
        elif tool in {"compare_topics_with_metrics", "test_text_metric_lag", "find_explanatory_segments"}:
            result = getattr(tools, tool)(**options)
        else:
            result = getattr(tools, tool)(data_path, dataset.snapshot_id, **options)
        projection = result.agent_projection()
        session = self._session(task_id)
        history = session.get("diagnostic_steps", [])
        if not isinstance(history, list):
            history = []
        history.append(projection)
        session["diagnostic_steps"] = history[-MAX_DIAGNOSTIC_STEPS:]
        self.workspace.save_task_artifact(task_id, "plugin_session", session)
        return projection

    def run_analysis_cycle(self, task_id: str) -> dict[str, object]:
        task = self._owned_task(task_id)
        result = self.workbench.start_run(MCP_OWNER, task.task_id, {"execute": True})
        run = result["run"]
        cycle = self.workspace.get_run_artifact(str(run["run_id"]), "analysis_cycle")
        if not isinstance(cycle, Mapping):
            raise WorkspaceStoreError("completed run did not persist an analysis cycle")
        persisted_cycle = AnalysisCycle.from_dict(cycle)
        return {
            "run_id": str(run["run_id"]),
            "cycle": dict(cycle),
            "artifact_refs": list(persisted_cycle.artifact_refs),
        }

    def resume_analysis_cycle(self, cycle_id: str) -> dict[str, object]:
        context = self.workspace.get_analysis_cycle_context(cycle_id)
        self._owned_task(str(context.get("task_id", "")))
        result = DemoCycleRunner(self.workspace).resume(cycle_id)
        return {
            "cycle": result.cycle.to_dict(),
            "artifact_refs": list(result.cycle.artifact_refs),
            "resumed": result.cycle.status == "completed",
        }

    def get_analysis_trace(self, task_id: str) -> dict[str, object]:
        task = self._owned_task(task_id)
        runs = self.workspace.list_runs(task.task_id)
        event_count = 0
        event_summaries = []
        artifact_refs: list[str] = []
        for run in runs[:20]:
            events = self.workspace.events_after(run.run_id, 0, 1000)
            event_count += len(events)
            for event in events[:50]:
                payload = event.to_dict()
                event_summaries.append(
                    {
                        "run_id": run.run_id,
                        "sequence": payload.get("sequence"),
                        "kind": payload.get("kind"),
                        "stage": payload.get("stage"),
                    }
                )
            cycle = self.workspace.get_run_artifact(run.run_id, "analysis_cycle")
            if isinstance(cycle, Mapping):
                artifact_refs.extend(AnalysisCycle.from_dict(cycle).artifact_refs)
        session = self._session(task_id)
        for item in session.get("diagnostic_steps", []):
            if isinstance(item, Mapping):
                artifact_refs.extend(str(ref) for ref in item.get("artifact_refs", []) if isinstance(ref, str))
        return {
            "task_id": task.task_id,
            "run_count": len(runs),
            "event_count": event_count,
            "artifact_refs": list(dict.fromkeys(artifact_refs))[:100],
            "events": event_summaries[:100],
            "diagnostic_steps": list(session.get("diagnostic_steps", []))[-20:],
            "snapshot_refs": [ref.to_dict() for ref in task.snapshot_refs],
        }

    def analyze_business_case(
        self,
        question: str,
        paths: Sequence[str],
        *,
        title: str | None = None,
        rules_path: str | None = None,
    ) -> dict[str, object]:
        created = self.create_analysis_task(question, paths, title=title, rules_path=rules_path)
        task_id = str(created["task_id"])
        execution = self.run_analysis_cycle(task_id)
        findings = []
        for metric in created["source_summary"]["metrics"][:MAX_METRIC_FINDINGS]:
            try:
                finding = self.analyze_task_metric(task_id, question, str(metric))
            except InputValidationError as error:
                findings.append({"metric": metric, "status": "unavailable", "limitation": str(error)[:300]})
                continue
            findings.append(
                {
                    "metric": metric,
                    "signal": finding["signal"],
                    "validation": finding["validation"],
                    "verification": finding["verification"],
                    "source": finding["context"].get("source", ""),
                }
            )
        verdicts = self.evaluate_task_rules(task_id)
        business_evidence = {
            "question": question,
            "metric_findings": findings,
            "rule_verdicts": verdicts,
        }
        self.workspace.save_run_artifact(str(execution["run_id"]), "business_evidence", business_evidence)
        return {
            "status": "completed",
            "task_id": task_id,
            "run_id": execution["run_id"],
            "cycle_id": execution["cycle"]["cycle_id"],
            "source_summary": created["source_summary"],
            "metric_findings": findings,
            "rule_verdicts": verdicts,
            "artifact_refs": execution["artifact_refs"],
        }

    def _owned_task(self, task_id: str) -> AnalysisTask:
        task = self.workspace.get_task_for_owner(task_id, MCP_OWNER)
        if task is None:
            raise WorkbenchApiError(HTTPStatus.NOT_FOUND, "task not found or not owned by this MCP host")
        return task

    def _session(self, task_id: str) -> dict[str, Any]:
        session = self.workspace.get_task_artifact(task_id, "plugin_session")
        return dict(session) if isinstance(session, Mapping) else {"diagnostic_steps": []}

    def _task_ruleset(self, task_id: str) -> RuleSet | None:
        flagship = self.workspace.get_task_artifact(task_id, "flagship_case")
        if isinstance(flagship, Mapping) and isinstance(flagship.get("rules"), Mapping):
            return parse_ruleset(dict(flagship["rules"]))
        session = self._session(task_id)
        path = session.get("rules_path")
        return load_ruleset(Path(str(path))) if isinstance(path, str) and path else None

    @staticmethod
    def _requested_paths(paths: Sequence[str]) -> tuple[Path, ...]:
        if not isinstance(paths, (list, tuple)) or not paths or any(not isinstance(path, str) or not path.strip() for path in paths):
            raise InputValidationError("paths must be a non-empty list of local source paths")
        approved = tuple(Path(path).expanduser().resolve() for path in paths)
        if any(not path.exists() for path in approved):
            raise InputValidationError("one or more requested source paths do not exist")
        return approved

    @staticmethod
    def _source_roots(paths: Sequence[Path]) -> tuple[Path, ...]:
        return tuple(dict.fromkeys(path if path.is_dir() else path.parent for path in paths))

    def _requested_flagship(self, paths: Sequence[Path]) -> str | None:
        for case in self.workbench.flagship_cases.list():
            package = self.workbench.flagship_cases.package(case.id)
            if any(path.is_dir() and path == package.root for path in paths):
                return case.id
        return None

    @staticmethod
    def _default_title(question: str, paths: Sequence[Path]) -> str:
        stem = paths[0].stem.replace("_", " ").replace("-", " ").strip()
        return f"{stem} · 业务分析" if stem else question[:120]

    def _managed_directory(self, task_id: str, child: str | None = None) -> Path:
        directory = self.workspace.path.parent / "plugin-sources" / task_id
        if child:
            directory /= child
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        return directory

    def _dataset_path(self, task_id: str, datasets: Sequence[ResolvedDataset], requested: Sequence[Path]) -> Path:
        files = self._requested_files(requested)
        if len(datasets) == 1 and datasets[0].origin == "file":
            candidate = next((path for path in files if path.name == datasets[0].name and path.suffix.lower() == ".csv"), None)
            if candidate is not None and hashlib.sha256(candidate.read_bytes()).hexdigest() == datasets[0].sha256:
                return candidate
        fields = list(dict.fromkeys(field for dataset in datasets for field in dataset.fields))
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for dataset in datasets:
            writer.writerows(dataset.rows)
        return self._write_private(self._managed_directory(task_id) / "materialized-metrics.csv", output.getvalue())

    def _document_paths(self, task_id: str, resolved: ResolvedSources, requested: Sequence[Path]) -> tuple[Path, ...]:
        files = self._requested_files(requested)
        paths = []
        for index, document in enumerate(resolved.documents, 1):
            original = next((path for path in files if path.name == document.name), None)
            if original is not None and original.suffix.lower() in {".md", ".txt"}:
                paths.append(original)
                continue
            text = "\n\n".join(
                f"# {section.heading}\n{section.text}" if section.heading else section.text
                for section in document.sections
            )
            stem = Path(document.name).stem
            paths.append(self._write_private(self._managed_directory(task_id, "documents") / f"{index:03d}-{stem}.md", text))
        return tuple(dict.fromkeys(paths))

    def _knowledge_root(self, task_id: str, documents: Sequence[Path]) -> Path:
        parents = {path.parent for path in documents}
        if len(parents) == 1:
            parent = next(iter(parents))
            present = {path.resolve() for path in parent.rglob("*") if path.is_file() and path.suffix.lower() in {".md", ".txt"}}
            if present == {path.resolve() for path in documents}:
                return parent
        target = self._managed_directory(task_id, "knowledge")
        for index, document in enumerate(documents, 1):
            self._write_private(target / f"{index:03d}-{document.name}", document.read_text(encoding="utf-8"))
        return target

    @staticmethod
    def _write_private(path: Path, content: str) -> Path:
        path.write_text(content, encoding="utf-8")
        os.chmod(path, 0o600)
        return path.resolve()

    @staticmethod
    def _requested_files(paths: Sequence[Path]) -> tuple[Path, ...]:
        result = []
        for path in paths:
            if path.is_dir():
                result.extend(candidate.resolve() for candidate in sorted(path.rglob("*")) if candidate.is_file())
            else:
                result.append(path)
        return tuple(dict.fromkeys(result))

    @staticmethod
    def _discover_rules(paths: Sequence[Path]) -> str:
        for path in paths:
            candidate = path / "rules.json" if path.is_dir() else path.parent / "rules.json"
            if candidate.is_file():
                load_ruleset(candidate)
                return str(candidate.resolve())
        return ""

    @staticmethod
    def _compact_insight(payload: dict[str, object]) -> dict[str, object]:
        context = payload.get("context")
        if isinstance(context, dict):
            context["source"] = Path(str(context.get("source", ""))).name
            context["excerpt"] = str(context.get("excerpt", ""))[:600]
        provenance = payload.get("provenance")
        if isinstance(provenance, dict):
            compact_sources = []
            for source in provenance.get("sources", []):
                if not isinstance(source, dict):
                    continue
                rows = source.get("rows", [])
                item = {"name": Path(str(source.get("path", ""))).name, "sha256": source.get("sha256", "")}
                if isinstance(rows, list) and rows:
                    item["row_count"] = len(rows)
                    item["row_span"] = [rows[0], rows[-1]]
                for key in ("start_line", "end_line"):
                    if source.get(key) is not None:
                        item[key] = source[key]
                compact_sources.append(item)
            provenance["sources"] = compact_sources
        payload["evidence"] = [
            f"来源：{item['name']}"
            for item in (provenance.get("sources", []) if isinstance(provenance, dict) else [])
        ]
        return payload


def _default_metric_spec(metric: str):
    from .metrics import MetricSpec

    return MetricSpec(name=metric)


def _json_safe(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False, default=lambda item: item.isoformat()))
