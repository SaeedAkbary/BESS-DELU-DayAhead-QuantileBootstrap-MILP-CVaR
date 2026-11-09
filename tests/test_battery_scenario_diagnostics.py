"""Tests for monthly scenario coverage diagnostics."""
import unittest

import numpy as np

from battery_scenario_diagnostics import scenario_diagnostics


class ScenarioDiagnosticTests(unittest.TestCase):
    def test_all_prices_inside_band(self):
        paths = np.vstack([np.zeros(96), np.full(96, 10.)])
        result = scenario_diagnostics([("2026-10-01", paths, np.full(96, 5.))])
        self.assertEqual(result["observed_band_coverage"], 1.)
        self.assertEqual(result["above_90_fraction"], 0.)
        self.assertEqual(result["below_10_fraction"], 0.)
        self.assertEqual(result["mean_signed_median_error_eur_mwh"], 0.)
        self.assertEqual(result["mean_band_width_eur_mwh"], 8.)

    def test_all_prices_above_band(self):
        paths = np.vstack([np.zeros(96), np.ones(96)])
        result = scenario_diagnostics([("2026-10-01", paths, np.full(96, 20.))])
        self.assertEqual(result["observed_band_coverage"], 0.)
        self.assertEqual(result["above_90_fraction"], 1.)
        self.assertEqual(result["mean_signed_median_error_eur_mwh"], 19.5)
        self.assertAlmostEqual(result["mean_band_width_eur_mwh"], 0.8)

    def test_rejects_invalid_paths(self):
        with self.assertRaises(ValueError):
            scenario_diagnostics([])
        with self.assertRaises(ValueError):
            scenario_diagnostics([("2026-10-01", np.zeros((2, 95)), np.zeros(96))])
        with self.assertRaises(ValueError):
            scenario_diagnostics([("2026-10-01", np.full((2, 96), np.nan), np.zeros(96))])


if __name__ == "__main__":
    unittest.main()
