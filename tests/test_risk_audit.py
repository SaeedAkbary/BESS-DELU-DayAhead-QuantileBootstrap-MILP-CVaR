"""Unit tests for price-tail diagnostics using synthetic fixtures only."""

import unittest
import numpy as np

# Test statistical functions without downloading data.
from risk_audit import risk_metrics


class PriceRiskAuditTests(unittest.TestCase):
    """Check extreme negatives, interval coverage, and array shapes."""

    def test_exact_scenarios_cover_the_actual(self):
        """Identical scenario paths must fully cover actual prices."""

        # Two synthetic days with three intervals each.
        actual = np.array([[10., -5., 20.], [12., 15., -2.]])
        # Repeat each actual path 50 times to verify calculations.
        paths = np.repeat(actual[:, None, :], repeats=50, axis=1)
        result = risk_metrics(actual, paths, -10., 25.)

        self.assertEqual(result["days_evaluated"], 2)
        self.assertEqual(result["intervals_evaluated"], 6)
        self.assertEqual(result["scenarios_per_day"], 50)
        self.assertAlmostEqual(result["scenario_p10_p90_coverage"], 1.0)
        self.assertAlmostEqual(result["below_scenario_p10_rate"], 0.0)
        self.assertAlmostEqual(result["above_scenario_p90_rate"], 0.0)
        self.assertFalse(result["risk_ready"])

    def test_extreme_negative_price_is_detected(self):
        """An extreme negative price must fall below the scenario lower tail."""

        # The third interval contains a synthetic extreme negative price.
        actual = np.array([[10., 10., -100.]])
        usual = np.array([9., 10., 11.])
        paths = np.repeat(usual[None, None, :], repeats=50, axis=1)
        result = risk_metrics(actual, paths, -50., 50.)

        self.assertAlmostEqual(result["below_scenario_p10_rate"], 1 / 3)
        self.assertAlmostEqual(
            result["extreme_interval_rates"]["below_training_p05_actual"], 1 / 3
        )
        self.assertAlmostEqual(
            result["extreme_interval_rates"]["below_training_p05_scenarios"], 0.0
        )

    def test_bad_shapes_are_rejected(self):
        """Reject mismatched day or interval dimensions."""

        actual = np.zeros((2, 3))
        paths = np.zeros((1, 50, 3))
        with self.assertRaises(ValueError):
            risk_metrics(actual, paths, -1., 1.)

    def test_nonfinite_prices_are_rejected(self):
        """Reject missing or infinite price values."""

        actual = np.array([[1., float("nan"), 3.]])
        paths = np.ones((1, 50, 3))
        with self.assertRaises(ValueError):
            risk_metrics(actual, paths, -1., 1.)


if __name__ == "__main__":
    unittest.main()
