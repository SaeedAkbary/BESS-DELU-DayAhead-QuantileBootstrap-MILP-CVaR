"""Scenario-generation unit tests using synthetic fixtures only."""

# Python standard-library test framework.
import unittest
# Use numpy and pandas for numeric and date checks.
import numpy as np
import pandas as pd

# Import only the functions under test.
from scenarios import prepare, sample_scenarios, calibration_gap, coverage_rate


class ScenarioTests(unittest.TestCase):
    """Check reproducibility and prevent target-day price leakage."""

    def test_daily_bootstrap_keeps_whole_paths(self):
        """Bootstrap complete historical daily paths, not individual hours."""

        # Three synthetic historical paths with four intervals each.
        paths = np.array([[1., 1., 1., 1.],
                          [-1., -1., -1., -1.],
                          [0.5, 0.5, 0.5, 0.5]])
        median = np.full(4, 50.)
        low = np.full(4, 49.)
        high = np.full(4, 51.)

        # Generate 20 scenarios with a fixed seed.
        result = sample_scenarios(median, low, high, paths, count=20, seed=7)
        self.assertEqual(result.shape, (20, 4))
        for row in result:
            self.assertTrue(any(np.allclose(row - median, p) for p in paths))

        # The same seed must produce identical results.
        other = sample_scenarios(median, low, high, paths, count=20, seed=7)
        np.testing.assert_array_equal(result, other)

    def test_calibration_gap_uses_only_known_errors(self):
        """Calibration should improve coverage of historical intervals."""

        # Two of four synthetic prices fall outside the raw interval.
        true_price = np.array([5., 10., 15., 20.])
        lower = np.array([7., 7., 7., 7.])
        upper = np.array([18., 18., 18., 18.])
        gap = calibration_gap(true_price, lower, upper, target_coverage=0.75)
        self.assertEqual(gap, 2.0)
        self.assertGreaterEqual(
            coverage_rate(true_price, lower - gap, upper + gap), 0.75
        )

    def test_calibration_does_not_mutate_predictions(self):
        """Calibration must not modify input predictions or bounds."""

        actual = np.array([5., 20.])
        low = np.array([7., 7.])
        high = np.array([18., 18.])
        old_low, old_high = low.copy(), high.copy()
        calibration_gap(actual, low, high)
        np.testing.assert_array_equal(low, old_low)
        np.testing.assert_array_equal(high, old_high)

    def test_previous_day_feature_does_not_see_target_price(self):
        """Target-day prices must not leak into same-day lagged features."""

        # Three synthetic regular days with distinct prices.
        times = pd.date_range("2026-01-12", periods=96 * 3, freq="15min",
                              tz="Europe/Berlin")
        prices = [10.] * 96 + [999.] * 96 + [20.] * 96
        fake = pd.DataFrame({"timestamp_utc": times.tz_convert("UTC"),
                             "price_eur_mwh": prices})
        # Use a temporary CSV to exercise the input parser.
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as folder:
            filename = Path(folder) / "test.csv"
            fake.to_csv(filename, index=False)
            result = prepare(filename)

        # Day two must use day-one prices (10), not its own prices (999).
        day_two = result[result["day"].astype(str) == "2026-01-13"]
        self.assertEqual(len(day_two), 96)
        self.assertTrue((day_two["prev_mean"] == 10.).all())

        # Day three must use day-two prices (999), not its own prices (20).
        day_three = result[result["day"].astype(str) == "2026-01-14"]
        self.assertTrue((day_three["prev_mean"] == 999.).all())


# Run tests when executed directly.
if __name__ == "__main__":
    unittest.main()
