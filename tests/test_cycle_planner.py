import json
from pathlib import Path
import tempfile
import time
import unittest

from data2doc2data.agents.base import AgentEvent, AgentSession
from data2doc2data.analysis_cycle import AnalysisCycle, AnalysisRound, RoundDecision
from data2doc2data.cycle_planner import (
    ConnectedCyclePlanner,
    MAX_PLANNER_PROMPT_BYTES,
    PLANNER_ENVELOPE_MARKER,
    PlannerWaiting,
)
from data2doc2data.flow_tools import REGISTERED_ANALYSIS_TOOLS


class FakeGateway:
    def __init__(self, response: str, *, fail: bool = False):
        self.response = response
        self.fail = fail
        self.messages: list[str] = []
        self.resume_ids: list[str | None] = []
        self.interrupted_sessions: list[str] = []

    def create_session(self, provider, workspace, resume_id=None):
        self.resume_ids.append(resume_id)
        return AgentSession("session-local", provider, resume_id or "provider-thread-1", workspace, resume_id is not None)

    def send(self, provider, session, message):
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("provider disconnected")
        yield AgentEvent("message.delta", {"text": self.response})
        yield AgentEvent("turn.completed", {})

    def interrupt(self, provider, session):
        self.interrupted_sessions.append(session.provider_session_id)


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
        envelope = json.loads(sent.split(PLANNER_ENVELOPE_MARKER + "\n", 1)[1])
        self.assertEqual(result.decision.action, "continue")
        self.assertNotIn("raw_rows", sent)
        self.assertNotIn("/Users/", sent)
        self.assertLessEqual(len(sent.encode("utf-8")), MAX_PLANNER_PROMPT_BYTES)
        self.assertEqual(result.provider_resume_id, "provider-thread-1")
        self.assertEqual(
            envelope["tool_contracts"]["segment_rank"]["required"],
            ["metric", "dimension"],
        )
        self.assertEqual(
            envelope["tool_contracts"]["segment_rank"]["optional"],
            ["split_date", "minimum_samples"],
        )
        self.assertEqual(envelope["allowed_prior_artifact_refs"], ["artifact-1"])
        self.assertIn("evidence_gaps 必须是 JSON 数组", sent)
        self.assertIn("continue 时 stop_reason 必须为 null", sent)
        self.assertIn("finish 时 tool 必须为 null 且 arguments 必须为 {}", sent)

    def test_disconnect_becomes_a_resumable_waiting_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = FakeGateway("", fail=True)
            planner = ConnectedCyclePlanner(gateway, "workbuddy", Path(directory), REGISTERED_ANALYSIS_TOOLS)

            with self.assertRaises(PlannerWaiting) as captured:
                planner.decide(AnalysisCycle.start("cycle-waiting"), (), provider_resume_id="prior-thread")

        self.assertEqual(captured.exception.provider_resume_id, "prior-thread")
        self.assertEqual(gateway.resume_ids, ["prior-thread"])

    def test_invalid_public_decision_becomes_a_resumable_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            gateway = FakeGateway("")
            planner = ConnectedCyclePlanner(gateway, "workbuddy", Path(directory), REGISTERED_ANALYSIS_TOOLS)

            with self.assertRaisesRegex(PlannerWaiting, "valid public decision") as captured:
                planner.decide(AnalysisCycle.start("cycle-invalid-response"), ())

            gateway.response = json.dumps(
                {
                    "round_number": 1,
                    "action": "finish",
                    "tool": None,
                    "arguments": {},
                    "rationale_summary": "公开证据已经足够。",
                    "prior_artifact_refs": [],
                    "evidence_gaps": [],
                    "stop_reason": "evidence_sufficient",
                },
                ensure_ascii=False,
            )
            result = planner.decide(AnalysisCycle.start("cycle-invalid-response"), ())

        self.assertIsNone(captured.exception.provider_resume_id)
        self.assertEqual(gateway.resume_ids, [None, None])
        self.assertIn("上一份公开决策未通过验证", gateway.messages[-1])
        self.assertIn("planner must return one JSON decision object", gateway.messages[-1])
        self.assertEqual(result.decision.action, "finish")

    def test_planner_parses_only_the_public_message_not_private_plan_deltas(self):
        response = json.dumps(
            {
                "round_number": 1,
                "action": "finish",
                "tool": None,
                "arguments": {},
                "rationale_summary": "公开证据已经足够。",
                "prior_artifact_refs": [],
                "evidence_gaps": [],
                "stop_reason": "evidence_sufficient",
            },
            ensure_ascii=False,
        )

        class ThoughtfulGateway(FakeGateway):
            def send(self, provider, session, message):
                self.messages.append(message)
                yield AgentEvent("plan.delta", {"text": "private reasoning that is not JSON"})
                yield AgentEvent("message.delta", {"text": response})
                yield AgentEvent("turn.completed", {})

        with tempfile.TemporaryDirectory() as directory:
            planner = ConnectedCyclePlanner(
                ThoughtfulGateway(response), "workbuddy", Path(directory), REGISTERED_ANALYSIS_TOOLS
            )

            result = planner.decide(AnalysisCycle.start("cycle-public-only"), ())

        self.assertEqual(result.decision.action, "finish")

    def test_total_turn_deadline_interrupts_active_private_planning(self):
        class ActiveGateway(FakeGateway):
            def send(self, provider, session, message):
                self.messages.append(message)
                time.sleep(0.05)
                if False:
                    yield AgentEvent("plan.delta", {"text": "still planning"})

        with tempfile.TemporaryDirectory() as directory:
            gateway = ActiveGateway("")
            planner = ConnectedCyclePlanner(
                gateway,
                "codex",
                Path(directory),
                REGISTERED_ANALYSIS_TOOLS,
                turn_deadline_seconds=0.01,
            )

            with self.assertRaisesRegex(PlannerWaiting, "deadline") as captured:
                planner.decide(AnalysisCycle.start("cycle-total-deadline"), ())

        self.assertEqual(captured.exception.provider_resume_id, "provider-thread-1")
        self.assertEqual(gateway.interrupted_sessions, ["provider-thread-1"])

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
