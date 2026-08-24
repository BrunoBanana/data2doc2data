import unittest

from data2doc2data.analysis_cycle import (
    AnalysisCycle,
    AnalysisRound,
    CyclePlanError,
    RoundDecision,
    validate_round_decision,
)


def decision(round_number: int, *, prior_refs: tuple[str, ...] = ()) -> RoundDecision:
    return RoundDecision(
        round_number=round_number,
        action="continue",
        tool="detect_anomalies" if round_number == 1 else "detect_change_points",
        arguments={"metric": "gmv"},
        rationale_summary="先识别异常，再根据产物补充结构变化检验。",
        prior_artifact_refs=prior_refs,
    )


class AnalysisCycleTests(unittest.TestCase):
    def test_revision_requires_a_prior_artifact_reference(self):
        with self.assertRaisesRegex(CyclePlanError, "prior artifact"):
            validate_round_decision(decision(2), {"detect_anomalies", "detect_change_points"})

    def test_cycle_stops_after_three_completed_rounds(self):
        cycle = AnalysisCycle.start("cycle-1", max_rounds=3)
        first = AnalysisRound.completed(decision(1), ("artifact-1",))
        second = AnalysisRound.completed(decision(2, prior_refs=("artifact-1",)), ("artifact-2",))
        third = AnalysisRound.completed(decision(3, prior_refs=("artifact-2",)), ("artifact-3",))

        cycle = cycle.complete_round(first).complete_round(second).complete_round(third)

        self.assertFalse(cycle.can_continue)
        self.assertEqual(cycle.status, "completed")
        self.assertEqual([item.round_number for item in cycle.rounds], [1, 2, 3])

    def test_finish_decision_requires_stop_reason_and_no_tool(self):
        invalid = RoundDecision(1, "finish", None, {}, "已有证据足够。")
        with self.assertRaisesRegex(CyclePlanError, "stop reason"):
            validate_round_decision(invalid, {"detect_anomalies"})

        valid = RoundDecision(1, "finish", None, {}, "已有证据足够。", stop_reason="evidence_sufficient")
        self.assertEqual(validate_round_decision(valid, {"detect_anomalies"}), valid)

    def test_revision_must_change_tool_or_arguments(self):
        first = decision(1)
        repeated = RoundDecision(
            2,
            "continue",
            "detect_anomalies",
            {"metric": "gmv"},
            "重复运行。",
            prior_artifact_refs=("artifact-1",),
        )

        with self.assertRaisesRegex(CyclePlanError, "revise"):
            validate_round_decision(repeated, {"detect_anomalies"}, prior_decision=first)

    def test_round_decision_rejects_raw_data_and_unregistered_tools(self):
        raw = RoundDecision(1, "continue", "detect_anomalies", {"rows": [{"gmv": 1}]}, "分析")
        arbitrary = RoundDecision(1, "continue", "python", {}, "执行")

        with self.assertRaisesRegex(CyclePlanError, "raw"):
            validate_round_decision(raw, {"detect_anomalies"})
        with self.assertRaisesRegex(CyclePlanError, "registered"):
            validate_round_decision(arbitrary, {"detect_anomalies"})


if __name__ == "__main__":
    unittest.main()
