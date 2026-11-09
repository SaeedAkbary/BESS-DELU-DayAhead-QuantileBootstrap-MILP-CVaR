"""Boundary and temporal-isolation tests for rolling monthly scenarios."""
import unittest
from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd

from battery_monthly_scenarios import month_bounds, build_month


class MonthlyScenarioTests(unittest.TestCase):
    def test_month_bounds_including_year_boundary(self):
        self.assertEqual(month_bounds("2026-12"),
                         (date(2026, 12, 1), date(2027, 1, 1)))
        self.assertEqual(month_bounds("2027-02"),
                         (date(2027, 2, 1), date(2027, 3, 1)))

    def test_invalid_month(self):
        with self.assertRaises(ValueError):
            month_bounds("2026-13")

    def test_rejects_unsupported_early_month(self):
        with self.assertRaises(ValueError):
            build_month(pd.DataFrame(), "2026-09")

    def test_no_target_prices_in_model_or_calibration(self):
        # Synthetic data: one day each for prior-month calibration and target.
        times = pd.date_range("2026-09-30", periods=96, freq="15min", tz="UTC")
        target = pd.date_range("2026-10-01", periods=96, freq="15min", tz="UTC")
        table = pd.DataFrame({
            "day": [date(2026, 9, 30)] * 96 + [date(2026, 10, 1)] * 96,
            "price_eur_mwh": [10.0] * 96 + [999.0] * 96,
        })
        seen_training = []
        def fake_fit(rows):
            seen_training.append(set(rows["day"]))
            return object()
        def fake_predict(model, rows):
            return (np.zeros(len(rows)), np.ones(len(rows)),
                    np.full(len(rows), 2.0))
        def fake_residuals(rows):
            return np.zeros((60, 96)), 0.0, 0.0, 0.0, None
        with patch("src.battery_monthly_scenarios.fit_quantiles", fake_fit), \
             patch("src.battery_monthly_scenarios.predict", fake_predict), \
             patch("src.battery_monthly_scenarios.past_residual_days", fake_residuals):
            result, meta = build_month(table, "2026-10")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(seen_training), 2)
        self.assertTrue(all(date(2026, 10, 1) not in days
                            for days in seen_training))
        self.assertEqual(meta["model_training_before"], "2026-10-01")

    def test_monthly_report_includes_daily_dispatch(self):
        from battery_monthly_scenarios import run
        from battery_optimization import Battery

        scenarios = np.zeros((2, 96))
        actual = np.zeros(96)
        fake_schedule = {
            "charge_mw": [0.0] * 96,
            "discharge_mw": [0.0] * 96,
            "energy_mwh": [1.0] * 97,
        }
        battery = Battery(2, 1, .95, .95, 1)
        with patch("scenarios.prepare", return_value=pd.DataFrame()), \
             patch("src.battery_monthly_scenarios.prepare", return_value=pd.DataFrame()), \
             patch("src.battery_monthly_scenarios.build_month",
                   return_value=([("2026-10-01", scenarios, actual)],
                                 {"month": "2026-10", "skipped_days": []})), \
             patch("src.battery_monthly_scenarios.scenario_diagnostics",
                   return_value={}), \
             patch("battery_optimization.stochastic",
                   return_value=fake_schedule), \
             patch("battery_optimization.perfect_foresight",
                   return_value=fake_schedule):
            report = run("unused.csv", "2026-10", battery)
        row = report["daily"][0]
        self.assertEqual(len(row["dispatch"]["1.0"]["charge_mw"]), 96)
        self.assertEqual(len(row["dispatch"]["1.0"]["energy_mwh"]), 97)
        self.assertEqual(row["dispatch"]["1.0"]["discharge_mw"], [0.0] * 96)
        self.assertEqual(row["1.0"], 0.0)



if __name__ == "__main__":
    unittest.main()
