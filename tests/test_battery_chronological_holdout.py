"""Unit tests for chronological selection without holdout leakage."""
import unittest

from battery_chronological_holdout import evaluate, WEIGHTS


class HoldoutSelectionTests(unittest.TestCase):
    def test_holdout_does_not_change_selected_lambda(self):
        daily = []
        for day in ("2026-10-01", "2026-10-02", "2026-10-16", "2026-10-17"):
            record = {"day": day, "oracle": 100.0}
            for w in WEIGHTS:
                record[w] = 20.0 if w == "1.0" else 10.0
            daily.append(record)
        report = {"alpha": .95, "daily": daily}
        first = evaluate(report)
        self.assertEqual(first["selected_lambda"], 1.0)
        # Changing holdout outcomes must not influence calibration selection.
        for row in daily[2:]:
            row["2.0"] = 100000.0
            row["1.0"] = -100000.0
        second = evaluate(report)
        self.assertEqual(second["selected_lambda"], 1.0)

    def test_equal_calibration_profit_favors_lower_weight(self):
        daily = []
        for day in ("2026-10-01", "2026-10-16"):
            row = {"day": day, "oracle": 0.0}
            row.update({w: 0.0 for w in WEIGHTS})
            daily.append(row)
        self.assertEqual(evaluate({"alpha": .95, "daily": daily})["selected_lambda"], 0.0)

    def test_missing_partition_raises(self):
        row = {"day": "2026-10-01", "oracle": 0.0}
        row.update({w: 0.0 for w in WEIGHTS})
        with self.assertRaises(ValueError):
            evaluate({"alpha": .95, "daily": [row]})


if __name__ == "__main__":
    unittest.main()
