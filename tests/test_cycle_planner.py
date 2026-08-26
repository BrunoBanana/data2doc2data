import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.agents.base import AgentEvent, AgentSession
from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
from data2doc2data.cycle_planner import ConnectedCyclePlanner, MAX_PLANNER_PROMPT_BYTES, PlannerWaiting
from data2doc2data.flow_tools import REGISTERED_ANALYSIS_TOOLS


class FakeGateway:
    def __init__(self, response: str, *, fail: bool = False):
        self.response = response
        self.fail = fail
        self.messages: list[str] = []
        self.resume_ids: list[str | None] = []

    def create_session(self, provider, workspace, resume_id=None):
        self.resume_ids.append(resume_id)
        return AgentSession("session-local", provider, resume_id or "provider-thread-1", workspace, resume_id is not None)

    def send(self, provider, session, message):
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("provider disconnected")
        yield AgentEvent("message.delta", {"text": self.response})
        yield AgentEvent("turn.completed", {})


class ConnectedCyclePlannerTests(unittest.TestCase):
    def test_planner_receives_only_a_bounded_derived_envelope(self):
        response = json.dumps(
            {
                "round_number": 2,
                "action": "continue",
                "tool": "detect_change_points",
                "arguments": {"metric": "gmv", "minimum_window": 3},
                "rationale_summary": "异常后检查结构变化。",
                "prior_artifact_refs": ["artifact-1"],
                "evidence_gaps": [],
                "stop_reason": None,
            },
            ensure_ascii=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            gateway = FakeGateway(response)
            planner = ConnectedCyclePlanner(gateway, "codex", Path(directory), REGISTERED_ANALYSIS_TOOLS)
            cycle = AnalysisCycle.start("cycle-connected").complete_round(
                AnalysisRound.completed(
                    RoundDecision(1, "continue", "detect_anomalies", {"metric": "gmv"}, "检查异常"),
                    ("artifact-1",),
                )
            )

            result = planner.decide(
                cycle,
                (
                    {
                        "tool": "detect_anomalies",
                        "status": "completed",
                        "summary": {"anomaly_count": 1, "raw_rows": [{"secret": 1}], "path": "/Users/private.csv"},
                        "artifact_refs": ["artifact-1"],
                    },
                ),
            )

        sent = gateway.messages[-1]
        self.assertEqual(result.decision.action, "continue")
        self.assertNotIn("raw_rows", sent)
        self.assertNotIn("/Users/", sent)
        self.assertLessEqual(len(sent.encode("utf-8")), MAX_PLANNER_PROMPT_BYTES)
        self.assertEqual(result.provider_resume_id, "provider-thread-1")

    def test_disconnect_becomes_a_resumable_waiting_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = FakeGateway("", fail=True)
            planner = ConnectedCyclePlanner(gateway, "workbuddy", Path(directory), REGISTERED_ANALYSIS_TOOLS)

            with self.assertRaises(PlannerWaiting) as captured:
                planner.decide(AnalysisCycle.start("cycle-waiting"), (), provider_resume_id="prior-thread")

        self.assertEqual(captured.exception.provider_resume_id, "prior-thread")
        self.assertEqual(gateway.resume_ids, ["prior-thread"])

    def test_planner_rejects_approval_requests_and_non_json_output(self):
        class ApprovalGateway(FakeGateway):
            def send(self, provider, session, message):
                self.messages.append(message)
                yield AgentEvent("approval.request", {"request_id": "approval-1", "operation": "write"})

        with tempfile.TemporaryDirectory() as directory:
            planner = ConnectedCyclePlanner(
                ApprovalGateway(""), "codex", Path(directory), REGISTERED_ANALYSIS_TOOLS
            )
            with self.assertRaisesRegex(PlannerWaiting, "approval"):
                planner.decide(AnalysisCycle.start("cycle-approval"), ())
