"""Synthetic validation of the battery optimization foundation."""
import unittest
import numpy as np
from battery_optimization import Battery, build_model, deterministic, stochastic, perfect_foresight


class BatteryOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.battery = Battery(capacity_mwh=2, power_mw=1,
                               eta_charge=1, eta_discharge=1,
                               initial_mwh=1)

    def test_bad_battery_rejected(self):
        with self.assertRaises(ValueError):
            build_model([10, 20], Battery(2, 1, 0, 1, 1))

    def test_price_shape_and_probabilities(self):
        with self.assertRaises(ValueError):
            build_model([[1, 2], [3, 4]], self.battery, probabilities=[0.9, 0.9])

    def test_charge_low_discharge_high(self):
        r = perfect_foresight([0, 100], self.battery, dt_hours=1)
        self.assertAlmostEqual(r["expected_profit_eur"], 100, places=5)
        self.assertAlmostEqual(r["energy_mwh"][-1], 1, places=5)

    def test_mean_equals_risk_neutral_stochastic(self):
        scenarios = np.array([[0, 100], [100, 0]], dtype=float)
        a = deterministic(scenarios, self.battery, dt_hours=1)
        b = stochastic(scenarios, self.battery, dt_hours=1, risk_weight=0)
        self.assertAlmostEqual(a["objective_eur"], b["objective_eur"], places=5)

    def test_fixed_schedule_under_cvar(self):
        scenarios = [[-100, 100], [100, -100]]
        r = stochastic(scenarios, self.battery, dt_hours=1, risk_weight=1, alpha=.9)
        self.assertEqual(len(r["charge_mw"]), 2)
        self.assertEqual(len(r["scenario_profit_eur"]), 2)


if __name__ == "__main__":
    unittest.main()
