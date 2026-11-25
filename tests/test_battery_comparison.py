"""Synthetic end-to-end test of scenario-to-battery comparison."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from battery_optimization import Battery
from battery_comparison import evaluate, realized_profit


class BatteryComparisonTests(unittest.TestCase):
    def test_realized_profit_uses_fixed_dispatch(self):
        schedule = {"charge_mw": [1, 0], "discharge_mw": [0, 1]}
        self.assertAlmostEqual(realized_profit(schedule, [10, 100], dt_hours=1), 90)

    def test_end_to_end_and_oracle_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            t = pd.date_range("2026-10-15", periods=4, freq="15min", tz="UTC")
            s = pd.DataFrame({
                "timestamp_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scenario_01": [10, 20, 80, 100],
                "scenario_02": [20, 10, 100, 80],
            })
            h = pd.DataFrame({
                "timestamp_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "price_eur_mwh": [10, 20, 80, 100],
            })
            sp, hp = Path(folder) / "s.csv", Path(folder) / "h.csv"
            s.to_csv(sp, index=False)
            h.to_csv(hp, index=False)
            battery = Battery(1, 1, 1, 1, .5)
            report = evaluate(sp, hp, battery, risk_weight=.5, alpha=.9)
            self.assertEqual(report["intervals"], 4)
            self.assertEqual(report["scenario_count"], 2)
            results = report["results"]
            oracle = results["perfect_foresight"]["realized_profit_eur"]
            self.assertGreaterEqual(oracle + 1e-6, results["deterministic"]["realized_profit_eur"])
            self.assertGreaterEqual(oracle + 1e-6, results["stochastic_cvar"]["realized_profit_eur"])


if __name__ == "__main__":
    unittest.main()
