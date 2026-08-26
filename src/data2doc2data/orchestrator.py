"""Compatibility facade for the unified observable Agent Flow engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .flow_engine import DemoFlowRunner, FlowExecutionResult
from .workspace import AnalysisTask
from .workspace_store import WorkspaceStore

OrchestrationResult = FlowExecutionResult


class AnalysisOrchestrator:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def run(
        self,
        task: AnalysisTask,
        data_path: Path,
        document_paths: tuple[Path, ...],
        proposal: dict[str, Any] | None = None,
    ) -> OrchestrationResult:
        return DemoFlowRunner(self.store).run(task, data_path, document_paths, proposal)
