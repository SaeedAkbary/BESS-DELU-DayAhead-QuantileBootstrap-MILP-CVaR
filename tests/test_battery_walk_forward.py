"""Synthetic tests for chronological multi-month risk selection."""
import unittest

from battery_walk_forward import evaluate_months
from battery_chronological_holdout import WEIGHTS


def report(month, profits=None, alpha=.95):
    values = profits or {}
    row = {"day": month + "-01", "oracle": 100.0}
    row.update({w: values.get(w, 1.0) for w in WEIGHTS})
    return {"month": month, "alpha": alpha, "battery": {"capacity_mwh": 2},
            "daily": [row]}


class WalkForwardTests(unittest.TestCase):
    def test_selection_uses_only_prior_months(self):
        jan = report("2026-01", {"1.0": 10.0, "0.0": 2.0})
        feb = report("2026-02", {"2.0": 100.0, "1.0": 3.0})
        first = evaluate_months([feb, jan])
        self.assertEqual(first["monthly"][0]["selected_lambda"], 1.0)
        self.assertEqual(first["monthly"][0]["selection_months"], ["2026-01"])
        self.assertEqual(first["monthly"][0]["selection_cutoff_exclusive"], "2026-02-01")
        self.assertEqual(first["monthly"][0]["selection_observation_count"], 1)
        feb["daily"][0]["2.0"] = 1000000.0
        second = evaluate_months([jan, feb])
        self.assertEqual(second["monthly"][0]["selected_lambda"], 1.0)

    def test_next_month_can_use_prior_outcome(self):
        jan = report("2026-01", {"1.0": 10.0})
        feb = report("2026-02", {"2.0": 100.0})
        mar = report("2026-03")
        result = evaluate_months([mar, feb, jan], lookback_months=1)
        self.assertEqual([x["selected_lambda"] for x in result["monthly"]],
                         [1.0, 2.0])
        self.assertEqual(result["evaluated_months"], 2)
        self.assertEqual(result["monthly"][1]["selection_months"], ["2026-02"])
        self.assertEqual(result["monthly"][1]["selection_cutoff_exclusive"], "2026-03-01")

    def test_rejects_duplicate_month(self):
        with self.assertRaises(ValueError):
            evaluate_months([report("2026-01"), report("2026-01")])

    def test_rejects_mismatched_alpha(self):
        with self.assertRaises(ValueError):
            evaluate_months([report("2026-01"), report("2026-02", alpha=.9)])

    def test_rejects_bad_day(self):
        with self.assertRaises(ValueError):
            evaluate_months([report("2026-01"), report("2026-02") | {
                "daily": [report("2026-03")["daily"][0]]}])

    def test_rejects_nonfinite_profit(self):
        for bad in (float("nan"), float("inf"), "100", True):
            with self.subTest(bad=bad):
                feb = report("2026-02")
                feb["daily"][0]["1.0"] = bad
                with self.assertRaises(ValueError):
                    evaluate_months([report("2026-01"), feb])

    def test_rejects_missing_calendar_month(self):
        with self.assertRaisesRegex(ValueError, "consecutive"):
            evaluate_months([report("2026-01"), report("2026-03")])

    def test_rejects_single_month(self):
        with self.assertRaises(ValueError):
            evaluate_months([report("2026-01")])


if __name__ == "__main__":
    unittest.main()
