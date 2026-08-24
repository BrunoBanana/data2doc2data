import tempfile
from pathlib import Path
import unittest

from data2doc2data.knowledge import KnowledgeError, KnowledgeLedger
from data2doc2data.workspace import AnalysisTask
from data2doc2data.workspace_store import WorkspaceStore


class KnowledgeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = WorkspaceStore(Path(self.temporary_directory.name) / "workbench.sqlite3")
        self.store.save_task(AnalysisTask.create("project-a", "项目 A", "积累可复用知识"))
        self.store.save_task(AnalysisTask.create("project-b", "项目 B", "隔离知识"))
        self.ledger = KnowledgeLedger(self.store)

    def test_candidate_keeps_provenance_but_is_excluded_from_verified_facts(self):
        candidate = self.ledger.propose(
            project_id="project-a",
            knowledge_id="knowledge-retention",
            statement="留存下降与激活率下降同时发生。",
            source_refs=("dataset-1", "document-1"),
            run_id="run-1",
            evidence_refs=("edge-1",),
            now="2026-08-24T01:00:00Z",
        )

        self.assertEqual(candidate.state, "candidate")
        self.assertEqual(candidate.source_refs, ("dataset-1", "document-1"))
        self.assertEqual(candidate.run_id, "run-1")
        self.assertEqual(self.ledger.verified_facts("project-a"), ())
        self.assertEqual(self.ledger.latest("project-b"), ())

    def test_verification_requires_deterministic_evidence_and_explicit_approval(self):
        self.ledger.propose(
            "project-a",
            "knowledge-1",
            "收入连续两期下降。",
            ("dataset-1",),
            "run-1",
            ("signal-1",),
            now="2026-08-24T01:00:00Z",
        )

        with self.assertRaisesRegex(KnowledgeError, "deterministic"):
            self.ledger.verify(
                "project-a",
                "knowledge-1",
                approved_by="analyst",
                deterministic_verified=False,
            )
        with self.assertRaisesRegex(KnowledgeError, "approval"):
            self.ledger.verify(
                "project-a",
                "knowledge-1",
                approved_by="",
                deterministic_verified=True,
            )
        self.ledger.propose(
            "project-a",
            "knowledge-no-evidence",
            "只有模型建议，尚无证据。",
            ("document-1",),
            "run-2",
            (),
            now="2026-08-24T01:00:00Z",
        )
        with self.assertRaisesRegex(KnowledgeError, "evidence"):
            self.ledger.verify(
                "project-a",
                "knowledge-no-evidence",
                approved_by="analyst",
                deterministic_verified=True,
            )

        verified = self.ledger.verify(
            "project-a",
            "knowledge-1",
            approved_by="analyst",
            deterministic_verified=True,
            evidence_refs=("validation-1",),
            now="2026-08-24T02:00:00Z",
        )

        self.assertEqual(verified.state, "verified")
        self.assertEqual(verified.valid_from, "2026-08-24T02:00:00Z")
        self.assertEqual(self.ledger.verified_facts("project-a"), (verified,))
        self.assertEqual(
            [item.state for item in self.ledger.history("project-a", "knowledge-1")], ["candidate", "verified"]
        )

    def test_rejection_and_superseding_are_append_only_and_project_scoped(self):
        self.ledger.propose(
            "project-a",
            "old",
            "旧口径",
            ("document-1",),
            "run-1",
            ("claim-1",),
            now="2026-08-24T01:00:00Z",
        )
        old = self.ledger.verify("project-a", "old", "analyst", True, now="2026-08-24T02:00:00Z")
        self.ledger.propose(
            "project-a",
            "new",
            "新口径",
            ("document-2",),
            "run-2",
            ("claim-2",),
            now="2026-08-24T02:30:00Z",
        )
        new = self.ledger.verify("project-a", "new", "analyst", True, now="2026-08-24T03:00:00Z")
        superseded = self.ledger.supersede(
            "project-a",
            "old",
            replacement_id="new",
            approved_by="analyst",
            reason="新制度生效",
            now="2026-08-24T04:00:00Z",
        )
        self.ledger.propose("project-b", "rejected", "不成立主张", ("document-3",), "run-3", ())
        rejected = self.ledger.reject(
            "project-b",
            "rejected",
            approved_by="reviewer",
            reason="缺少数据证据",
        )

        self.assertEqual(old.state, "verified")
        self.assertEqual(new.state, "verified")
        self.assertEqual(superseded.state, "superseded")
        self.assertEqual(superseded.replacement_id, "new")
        self.assertEqual(superseded.valid_to, "2026-08-24T04:00:00Z")
        self.assertEqual(rejected.state, "rejected")
        self.assertEqual([item.knowledge_id for item in self.ledger.verified_facts("project-a")], ["new"])
        self.assertEqual(self.ledger.verified_facts("project-b"), ())


if __name__ == "__main__":
    unittest.main()
