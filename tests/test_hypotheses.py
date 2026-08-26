from datetime import date
import unittest

from data2doc2data.hypotheses import (
    HypothesisClause,
    HypothesisSpec,
    parse_controlled_hypothesis,
    validate_hypothesis_payload,
    verify_hypothesis,
)
from data2doc2data.metrics import InputValidationError, MetricRow


class HypothesisTests(unittest.TestCase):
    def test_parser_preserves_chinese_metric_subjects_and_directions(self):
        hypothesis = parse_controlled_hypothesis("激活率上升，同时留存率下降")

        self.assertEqual(
            [(clause.metric, clause.direction) for clause in hypothesis.clauses],
            [("activation_rate", "up"), ("retention_rate", "down")],
        )

    def test_parser_preserves_english_metric_subjects_and_directions(self):
        hypothesis = parse_controlled_hypothesis("Activation rises while retention falls.")

        self.assertEqual(
            [(clause.metric, clause.direction) for clause in hypothesis.clauses],
            [("activation_rate", "up"), ("retention_rate", "down")],
        )

    def test_parser_rejects_negated_or_ambiguous_text(self):
        self.assertIsNone(parse_controlled_hypothesis("不能说明激活率上升导致留存率下降"))
        self.assertIsNone(parse_controlled_hypothesis("Activation and retention changed."))
        self.assertIsNone(
            parse_controlled_hypothesis("Activation rises, activation falls, and retention falls.")
        )

    def test_agent_payload_is_validated_into_typed_hypothesis(self):
        hypothesis = validate_hypothesis_payload(
            {
                "clauses": [
                    {"metric": "conversion_rate", "direction": "up"},
                    {"metric": "revenue", "direction": "down"},
                ],
                "time_relation": "same_window",
                "source": "agent_proposed",
            }
        )

        self.assertEqual(hypothesis.source, "agent_proposed")
        self.assertEqual(hypothesis.clauses[1].metric, "revenue")

    def test_agent_payload_rejects_unknown_directions(self):
        with self.assertRaisesRegex(InputValidationError, "direction"):
            validate_hypothesis_payload(
                {"clauses": [{"metric": "revenue", "direction": "volatile"}]}
            )

    def test_typed_hypothesis_rejects_an_empty_clause_list(self):
        with self.assertRaisesRegex(InputValidationError, "clause"):
            HypothesisSpec(clauses=())

    def test_generic_verifier_returns_clause_level_results(self):
        hypothesis = HypothesisSpec(
            clauses=(
                HypothesisClause("conversion_rate", "up"),
                HypothesisClause("revenue", "down"),
            )
        )
        rows = [
            MetricRow(date(2026, 1, 1), "conversion_rate", 0.10),
            MetricRow(date(2026, 1, 2), "conversion_rate", 0.20),
            MetricRow(date(2026, 1, 1), "revenue", 100.0),
            MetricRow(date(2026, 1, 2), "revenue", 80.0),
        ]

        result = verify_hypothesis(hypothesis, rows)

        self.assertEqual(result.status, "confirmed")
        self.assertEqual(
            [(clause.metric, clause.status) for clause in result.clauses],
            [("conversion_rate", "confirmed"), ("revenue", "confirmed")],
        )

    def test_generic_verifier_reports_unavailable_metrics(self):
        hypothesis = HypothesisSpec(clauses=(HypothesisClause("revenue", "up"),))

        result = verify_hypothesis(hypothesis, [])

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.clauses[0].status, "unavailable")


if __name__ == "__main__":
    unittest.main()
