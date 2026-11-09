"""Independent physics and objective checks for the battery MILP.

All inputs here are synthetic; no claim is made about the real installation.
"""
import unittest

from battery_optimization import Battery, solve_dispatch, stochastic


class PhysicsAudit(unittest.TestCase):
    def test_energy_balance_efficiency_and_cyclic_terminal(self):
        battery = Battery(2, 1, .8, .9, .5, variable_cost_eur_mwh=0)
        result = solve_dispatch([0, 0, 100, 100], battery, dt_hours=.25)
        energy = result["energy_mwh"]
        charge = result["charge_mw"]
        discharge = result["discharge_mw"]
        self.assertAlmostEqual(energy[0], .5, places=6)
        self.assertAlmostEqual(energy[-1], .5, places=6)
        for t in range(4):
            self.assertGreaterEqual(energy[t], -1e-6)
            self.assertLessEqual(energy[t], 2 + 1e-6)
            self.assertLessEqual(charge[t], 1 + 1e-6)
            self.assertLessEqual(discharge[t], 1 + 1e-6)
            self.assertLessEqual(min(charge[t], discharge[t]), 1e-6)
            expected = energy[t] + .25 * (.8 * charge[t] - discharge[t] / .9)
            self.assertAlmostEqual(energy[t + 1], expected, places=6)

    def test_manual_profit_including_variable_om(self):
        battery = Battery(2, 1, 1, 1, 1, variable_cost_eur_mwh=5)
        prices = [0, 100]
        result = solve_dispatch(prices, battery, dt_hours=1)
        charge = result["charge_mw"]
        discharge = result["discharge_mw"]
        manual = sum(prices[t] * (discharge[t] - charge[t])
                     - 5 * (charge[t] + discharge[t]) for t in range(2))
        self.assertAlmostEqual(result["expected_profit_eur"], manual, places=6)
        self.assertAlmostEqual(manual, 90, places=6)

    def test_cvar_penalty_is_analytically_correct(self):
        # A single-period, fixed-energy battery cannot dispatch; loss CVaR is zero.
        battery = Battery(1, 1, 1, 1, 0)
        result = stochastic([[-100], [100]], battery,
                            dt_hours=1, risk_weight=2, alpha=.95)
        self.assertAlmostEqual(result["expected_profit_eur"], 0, places=6)
        self.assertAlmostEqual(result["objective_eur"], 0, places=6)

    def test_risk_neutral_objective_equals_scenario_mean(self):
        battery = Battery(2, 1, 1, 1, 1)
        paths = [[0, 100], [20, 80]]
        result = stochastic(paths, battery, dt_hours=1, risk_weight=0)
        profits = result["scenario_profit_eur"]
        self.assertAlmostEqual(result["expected_profit_eur"],
                               sum(profits) / 2, places=6)


if __name__ == "__main__":
    unittest.main()
