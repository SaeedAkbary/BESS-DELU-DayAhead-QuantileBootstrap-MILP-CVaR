import unittest
from src.battery_metrics import summarize_net


class MetricTests(unittest.TestCase):
    def test_fractional_tail_and_var(self):
        # Losses -10, 0, 10, 30; worst 37.5% = (30 + .5*10)/1.5.
        row = summarize_net([10, 0, -10, -30], alpha=.625)
        self.assertEqual(row["empirical_var_loss_eur"], 10)
        self.assertAlmostEqual(row["empirical_cvar_loss_eur"], 35 / 1.5)
        self.assertEqual(row["negative_profit_days_pct"], 50)
        self.assertEqual(row["mean_daily_profit_eur"], -7.5)
        self.assertEqual(row["median_daily_profit_eur"], -5)
        self.assertAlmostEqual(row["std_daily_profit_eur"], (218.75) ** .5)

    def test_drawdown_includes_starting_zero(self):
        row = summarize_net([-5, 10, -3, -9, 4])
        self.assertEqual(row["drawdown_eur"], [5, 0, 3, 12, 8])
        self.assertEqual(row["maximum_drawdown_eur"], 12)

    def test_ties_singleton_and_all_profitable(self):
        self.assertEqual(summarize_net([4])["empirical_cvar_loss_eur"], -4)
        self.assertEqual(summarize_net([4, 4])["worst_daily_net_loss_eur"], 0)
        self.assertEqual(summarize_net([0, 0])["maximum_drawdown_eur"], 0)

    def test_invalid_and_zero_volume(self):
        for x in ([], [float("inf")], [float("nan")]):
            with self.assertRaises(ValueError):
                summarize_net(x)
        record = {"net_profit_eur": 0, "discharge_throughput_mwh": 0}
        self.assertIsNone(summarize_net([0], accounting=[record])["net_profit_per_mwh_discharged"])
        with self.assertRaises(ValueError):
            summarize_net([1], accounting=[record])
