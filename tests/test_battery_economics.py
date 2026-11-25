"""Hand-calculated accounting, objective and failure regressions."""
import unittest
from dataclasses import replace
from unittest.mock import patch, Mock
import numpy as np
from battery_optimization import Battery, solve_dispatch, stochastic
from battery_comparison import realized_profit
from src.battery_economics import account_dispatch, COST_FIELDS


class EconomicsTests(unittest.TestCase):
    def setUp(self):
        self.battery = Battery(2, 1, 1, 1, 1, variable_cost_eur_mwh=2,
            purchase_fee_eur_mwh=3, sale_fee_eur_mwh=4,
            execution_cost_eur_mwh=5, degradation_eur_mwh_discharged=6)

    def test_quarter_hour_reconciliation(self):
        row = account_dispatch({"charge_mw": [1, 0], "discharge_mw": [0, 1]},
                               [-20, 100], self.battery)
        self.assertEqual(row["energy_purchase_cost_eur"], -5)
        self.assertEqual(row["gross_arbitrage_profit_eur"], 30)
        self.assertEqual(row["transaction_costs_eur"], 1.75)
        self.assertEqual(row["degradation_costs_eur"], 1.5)
        self.assertEqual(row["other_variable_costs_eur"], 3.5)
        self.assertEqual(row["net_profit_eur"], 23.25)
        self.assertEqual(row["discharge_throughput_mwh"], .25)

    def test_objective_matches_scoring_and_oracle(self):
        paths = [[-20, 100], [0, 80]]
        schedule = stochastic(paths, self.battery, dt_hours=.5, risk_weight=.5, alpha=.5)
        profits = [realized_profit(schedule, p, .5, battery=self.battery) for p in paths]
        np.testing.assert_allclose(profits, schedule["scenario_profit_eur"])
        self.assertAlmostEqual(schedule["objective_eur"], np.mean(profits) + .5 * min(profits))
        for p, profit in zip(paths, profits):
            self.assertGreaterEqual(solve_dispatch(p, self.battery, dt_hours=.5)["objective_eur"] + 1e-7, profit)

    def test_zero_cost_compatibility(self):
        battery = Battery(2, 1, 1, 1, 1)
        schedule = solve_dispatch([0, 100], battery, dt_hours=1)
        self.assertAlmostEqual(schedule["objective_eur"], 100)
        self.assertAlmostEqual(realized_profit(schedule, [0, 100], 1), 100)
        self.assertAlmostEqual(realized_profit(schedule, [0, 100], 1, 5), 90)
        with self.assertRaises(ValueError):
            realized_profit(schedule, [0, 100], battery=battery, variable_cost=5)

    def test_expensive_dispatch_prefers_zero(self):
        battery = replace(self.battery, degradation_eur_mwh_discharged=1000)
        for prices in ([0, 100], [0, 0], [-10, -10]):
            schedule = solve_dispatch(prices, battery, dt_hours=1)
            self.assertAlmostEqual(sum(schedule["charge_mw"] + schedule["discharge_mw"]), 0)

    def test_invalid_economic_parameters(self):
        for field in COST_FIELDS:
            for bad in (-1, float("nan"), float("inf"), True):
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    replace(self.battery, **{field: bad}).validate()
        for bad in (0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                solve_dispatch([1, 2], self.battery, dt_hours=bad)

    def test_infeasible_and_missing_solver(self):
        with self.assertRaisesRegex(RuntimeError, "optimality"):
            solve_dispatch([0], Battery(2, .1, 1, 1, 0, terminal_mwh=2))
        solver = Mock()
        solver.available.return_value = False
        with patch("pyomo.environ.SolverFactory", return_value=solver):
            with self.assertRaisesRegex(RuntimeError, "solver"):
                solve_dispatch([0], self.battery)

    def test_nonfinite_scoring_rejected(self):
        for prices in ([float("nan")], [float("inf")]):
            with self.assertRaises(ValueError):
                account_dispatch({"charge_mw": [0], "discharge_mw": [0]}, prices, self.battery)
