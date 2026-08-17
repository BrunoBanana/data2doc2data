import json
from pathlib import Path
import tempfile
import unittest

from data2doc2data.metrics import InputValidationError
from data2doc2data.rules import (
    MAX_RULES_BYTES,
    default_ruleset,
    load_ruleset,
    parse_ruleset,
)


VALID_RULESET = {
    "version": 1,
    "metrics": {
        "revenue": {"aliases": ["收入", "营收"], "display_name": "收入", "aggregation": "sum"},
        "churn_rate": {"aliases": ["流失率", "churn"], "display_name": "流失率"},
    },
    "rules": [
        {
            "id": "revenue-churn-tradeoff",
            "name": "收入与流失权衡",
            "description": "收入上升但流失率上升时提示增长质量问题",
            "clauses": [
                {"metric": "revenue", "direction": "up"},
                {"metric": "churn_rate", "direction": "up"},
            ],
        }
    ],
}


class DefaultRulesetTests(unittest.TestCase):
    def test_default_ruleset_reproduces_builtin_metrics(self):
        ruleset = default_ruleset()

        self.assertEqual(ruleset.aliases()["retention_rate"], ("retention", "retention rate", "留存", "留存率"))
        self.assertEqual(ruleset.display_name("retention_rate"), "留存率")
        self.assertEqual(ruleset.spec_for("retention_rate").name, "retention_rate")

    def test_default_ruleset_has_no_named_rules(self):
        self.assertEqual(default_ruleset().rules, ())

    def test_spec_for_unknown_metric_falls_back_to_plain_spec(self):
        self.assertEqual(default_ruleset().spec_for("unknown_metric").name, "unknown_metric")
        self.assertEqual(default_ruleset().display_name("unknown_metric"), "unknown_metric")


class ParseRulesetTests(unittest.TestCase):
    def test_valid_ruleset_parses(self):
        ruleset = parse_ruleset(VALID_RULESET)

        self.assertEqual(sorted(ruleset.metrics), ["churn_rate", "revenue"])
        self.assertEqual(ruleset.metrics["revenue"].aggregation, "sum")
        self.assertEqual(len(ruleset.rules), 1)
        rule = ruleset.rules[0]
        self.assertEqual(rule.rule_id, "revenue-churn-tradeoff")
        self.assertEqual(rule.metric_set(), frozenset({"revenue", "churn_rate"}))

    def test_payload_must_be_an_object(self):
        with self.assertRaisesRegex(InputValidationError, "must be a JSON object"):
            parse_ruleset(["revenue"])

    def test_unsupported_version_is_rejected(self):
        with self.assertRaisesRegex(InputValidationError, "version"):
            parse_ruleset({"version": 2, "metrics": {"x": {}}})

    def test_metrics_must_be_a_nonempty_object(self):
        with self.assertRaisesRegex(InputValidationError, "metrics"):
            parse_ruleset({"version": 1})

    def test_invalid_metric_name_is_rejected(self):
        with self.assertRaisesRegex(InputValidationError, "metric name"):
            parse_ruleset({"version": 1, "metrics": {"bad name!": {}}})

    def test_duplicate_metric_definition_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {}, "REVENUE": {}}}
        with self.assertRaisesRegex(InputValidationError, "duplicate metric"):
            parse_ruleset(payload)

    def test_invalid_aggregation_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {"aggregation": "median"}}}
        with self.assertRaisesRegex(InputValidationError, "aggregation"):
            parse_ruleset(payload)

    def test_boolean_threshold_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {"threshold": True}}}
        with self.assertRaisesRegex(InputValidationError, "threshold"):
            parse_ruleset(payload)

    def test_negative_threshold_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {"threshold": -1.0}}}
        with self.assertRaisesRegex(InputValidationError, "threshold"):
            parse_ruleset(payload)

    def test_minimum_observations_below_two_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {"minimum_observations": 1}}}
        with self.assertRaisesRegex(InputValidationError, "minimum_observations"):
            parse_ruleset(payload)

    def test_rule_referencing_undeclared_metric_is_rejected(self):
        payload = {
            "version": 1,
            "metrics": {"revenue": {}},
            "rules": [{"id": "r", "name": "r", "clauses": [{"metric": "nope", "direction": "up"}]}],
        }
        with self.assertRaisesRegex(InputValidationError, "undeclared metric"):
            parse_ruleset(payload)

    def test_rule_with_invalid_direction_is_rejected(self):
        payload = {
            "version": 1,
            "metrics": {"revenue": {}},
            "rules": [{"id": "r", "name": "r", "clauses": [{"metric": "revenue", "direction": "sideways"}]}],
        }
        with self.assertRaisesRegex(InputValidationError, "direction"):
            parse_ruleset(payload)

    def test_duplicate_rule_id_is_rejected(self):
        payload = {
            "version": 1,
            "metrics": {"revenue": {}},
            "rules": [
                {"id": "dup", "name": "a", "clauses": [{"metric": "revenue", "direction": "up"}]},
                {"id": "dup", "name": "b", "clauses": [{"metric": "revenue", "direction": "down"}]},
            ],
        }
        with self.assertRaisesRegex(InputValidationError, "duplicate rule id"):
            parse_ruleset(payload)

    def test_duplicate_metric_set_across_rules_is_rejected(self):
        payload = {
            "version": 1,
            "metrics": {"revenue": {}},
            "rules": [
                {"id": "a", "name": "a", "clauses": [{"metric": "revenue", "direction": "up"}]},
                {"id": "b", "name": "b", "clauses": [{"metric": "revenue", "direction": "down"}]},
            ],
        }
        with self.assertRaisesRegex(InputValidationError, "duplicate rule for metric set"):
            parse_ruleset(payload)

    def test_rule_without_clauses_is_rejected(self):
        payload = {"version": 1, "metrics": {"revenue": {}}, "rules": [{"id": "r", "name": "r", "clauses": []}]}
        with self.assertRaisesRegex(InputValidationError, "clauses"):
            parse_ruleset(payload)

    def test_rule_repeating_a_metric_is_rejected(self):
        payload = {
            "version": 1,
            "metrics": {"revenue": {}},
            "rules": [
                {
                    "id": "r",
                    "name": "r",
                    "clauses": [
                        {"metric": "revenue", "direction": "up"},
                        {"metric": "revenue", "direction": "down"},
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(InputValidationError, "repeats metric"):
            parse_ruleset(payload)


class MatchRuleTests(unittest.TestCase):
    def test_match_by_metric_set_ignores_direction(self):
        ruleset = parse_ruleset(VALID_RULESET)
        from data2doc2data.hypotheses import HypothesisClause, HypothesisSpec

        hypothesis = HypothesisSpec(
            (HypothesisClause("revenue", "down"), HypothesisClause("churn_rate", "flat"))
        )
        matched = ruleset.match_rule(hypothesis)

        self.assertIsNotNone(matched)
        self.assertEqual(matched.rule_id, "revenue-churn-tradeoff")

    def test_no_match_when_metric_set_differs(self):
        ruleset = parse_ruleset(VALID_RULESET)
        from data2doc2data.hypotheses import HypothesisClause, HypothesisSpec

        hypothesis = HypothesisSpec((HypothesisClause("revenue", "up"),))
        self.assertIsNone(ruleset.match_rule(hypothesis))


class AnalysisIntegrationTests(unittest.TestCase):
    """The ruleset drives the full evidence loop beyond the built-in metrics."""

    def test_custom_ruleset_verdicts_a_documented_rule(self):
        from data2doc2data.analysis import analyze
        from data2doc2data.config import Profile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text(
                "date,metric,value\n"
                "2026-01-05,revenue,100\n"
                "2026-01-06,revenue,120\n"
                "2026-01-05,churn_rate,0.1\n"
                "2026-01-06,churn_rate,0.2\n",
                encoding="utf-8",
            )
            (notes / "decision.md").write_text(
                "本季度收入上升，同时流失率上升，需要关注增长质量。",
                encoding="utf-8",
            )
            profile = Profile("local", str(csv_path), str(notes))
            ruleset = parse_ruleset(VALID_RULESET)

            result = analyze("收入发生了什么变化？", profile, ruleset=ruleset)

            self.assertEqual(result.signal.metric, "revenue")
            self.assertEqual(result.verification.rule_id, "revenue-churn-tradeoff")
            self.assertEqual(result.verification.rule_name, "收入与流失权衡")
            self.assertEqual(result.verification.status, "confirmed")

    def test_rule_contradicted_by_opposite_data_direction(self):
        from data2doc2data.analysis import analyze
        from data2doc2data.config import Profile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "metrics.csv"
            notes = root / "notes"
            notes.mkdir()
            csv_path.write_text(
                "date,metric,value\n"
                "2026-01-05,revenue,100\n"
                "2026-01-06,revenue,120\n"
                "2026-01-05,churn_rate,0.2\n"
                "2026-01-06,churn_rate,0.1\n",
                encoding="utf-8",
            )
            (notes / "decision.md").write_text(
                "本季度收入上升，同时流失率上升，需要关注增长质量。",
                encoding="utf-8",
            )
            profile = Profile("local", str(csv_path), str(notes))

            result = analyze("收入发生了什么变化？", profile, ruleset=parse_ruleset(VALID_RULESET))

            self.assertEqual(result.verification.rule_id, "revenue-churn-tradeoff")
            self.assertEqual(result.verification.status, "not_confirmed")


class LoadRulesetTests(unittest.TestCase):
    def test_load_missing_file_raises(self):
        with self.assertRaisesRegex(InputValidationError, "does not exist"):
            load_ruleset(Path("/nonexistent/rules.json"))

    def test_load_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(InputValidationError, "cannot read rules"):
                load_ruleset(path)

    def test_load_oversized_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_bytes(b" " * (MAX_RULES_BYTES + 1))
            with self.assertRaisesRegex(InputValidationError, "too large"):
                load_ruleset(path)

    def test_load_valid_file_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps(VALID_RULESET, ensure_ascii=False), encoding="utf-8")
            ruleset = load_ruleset(path)
            self.assertEqual(ruleset.rules[0].rule_id, "revenue-churn-tradeoff")


if __name__ == "__main__":
    unittest.main()
