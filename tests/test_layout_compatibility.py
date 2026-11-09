"""Regression checks for legacy import paths after the layout refactor."""
import subprocess
import sys
import unittest
import numpy as np

import battery_optimization as legacy_battery
import battery_uncertainty as legacy_uncertainty
import scenarios as legacy_scenarios
from src import battery_optimization, battery_uncertainty, scenarios


class LayoutCompatibilityTests(unittest.TestCase):
    def test_legacy_and_package_cli_help_match(self):
        """CLI entry points must remain usable after moving implementation files."""
        for legacy, package in (
            ("scenarios.py", "src.scenarios"),
            ("extend_price_history.py", "src.extend_price_history"),
            ("run_battery_walk_forward.py", "scripts.run_battery_walk_forward"),
        ):
            with self.subTest(command=legacy):
                old = subprocess.run(
                    [sys.executable, legacy, "--help"],
                    capture_output=True, text=True, check=True,
                )
                new = subprocess.run(
                    [sys.executable, "-m", package, "--help"],
                    capture_output=True, text=True, check=True,
                )
                self.assertEqual(old.stdout, new.stdout)
                self.assertIn("usage:", old.stdout)

    def test_battery_api_is_same_implementation(self):
        self.assertIs(legacy_battery.Battery, battery_optimization.Battery)
        self.assertIs(legacy_battery.build_model, battery_optimization.build_model)
        self.assertIs(legacy_battery.deterministic, battery_optimization.deterministic)
        self.assertIs(legacy_battery.stochastic, battery_optimization.stochastic)

    def test_bootstrap_results_match_exactly(self):
        daily = [
            {"selected": 12.0, "risk_neutral": 9.0},
            {"selected": 5.0, "risk_neutral": 7.0},
            {"selected": 20.0, "risk_neutral": 11.0},
        ]
        kwargs = {"seed": 17, "n_boot": 250}
        self.assertEqual(
            legacy_uncertainty.paired_profit_bootstrap(daily, **kwargs),
            battery_uncertainty.paired_profit_bootstrap(daily, **kwargs),
        )

    def test_price_scenario_samples_match_exactly(self):
        median = np.array([50.0, 60.0, 55.0, 40.0])
        low = median - 10
        high = median + 10
        residuals = np.array([[1., 2., 3., 4.], [-2., -1., 0., 1.]])
        kwargs = {"count": 20, "seed": 19}
        np.testing.assert_array_equal(
            legacy_scenarios.sample_scenarios(median, low, high, residuals, **kwargs),
            scenarios.sample_scenarios(median, low, high, residuals, **kwargs),
        )


if __name__ == "__main__":
    unittest.main()
