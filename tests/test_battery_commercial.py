"""Integrated commercial workflow tests using clearly synthetic inputs."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

from src.battery_config import validate_config, experiment_configs
from src.battery_validation import validate_report_calendar, validate_month_table
from battery_walk_forward import evaluate_months
from battery_optimization import Battery
from battery_monthly_scenarios import evaluate_inputs, build_month
from scripts.run_commercial_backtest import compare_reports, run_experiments
from src.battery_commercial_report import render_report, write_pending_report
from scenarios import prepare
from tests.test_battery_walk_forward import report


class CommercialTests(unittest.TestCase):
    def test_economic_selection_and_target_invariance(self):
        jan = report("2026-01", {"0.0": 20., "1.0": 5.})
        jan["daily"].append({**jan["daily"][0], "day": "2026-01-02", "0.0": -10.})
        feb = report("2026-02")
        kwargs = dict(require_complete=False, selection_rule="net_downside", downside_penalty=1.)
        selected = evaluate_months([jan, feb], **kwargs)
        self.assertEqual(selected["monthly"][0]["selected_lambda"], 1.)
        self.assertEqual(evaluate_months([jan, feb], require_complete=False)["monthly"][0]["selected_lambda"], 0.)
        feb["daily"][0]["2.0"] = 1e9
        self.assertEqual(evaluate_months([jan, feb], **kwargs)["monthly"][0]["selected_lambda"], 1.)

    def test_report_calendar_and_incomplete_november(self):
        with self.assertRaisesRegex(ValueError, "every calendar day"):
            validate_report_calendar(report("2026-10"), today=date(2026, 11, 23))
        with self.assertRaisesRegex(ValueError, "not complete"):
            validate_report_calendar(report("2026-11"), today=date(2026, 11, 23))
        complete = report("2026-10")
        complete["skipped_days"] = [{"day": f"2026-10-{d:02d}", "reason": "fixture exclusion"} for d in range(2, 32)]
        validate_report_calendar(complete, today=date(2026, 11, 23))
        complete["skipped_days"].append({"day": "2026-10-01", "reason": "overlap"})
        with self.assertRaises(ValueError):
            validate_report_calendar(complete)

    def test_missing_days_intervals_and_nonfinite_prices(self):
        times = pd.date_range("2026-09-01", "2026-10-01", freq="15min", inclusive="left", tz="Europe/Berlin")
        frame = pd.DataFrame({"timestamp_utc": times.tz_convert("UTC"), "price_eur_mwh": 10.})
        validate_month_table(frame, "2026-09")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            for broken in (frame.drop(index=10), frame.iloc[96:], frame.assign(price_eur_mwh=float("inf"))):
                broken.to_csv(path, index=False)
                with self.assertRaises(ValueError):
                    validate_month_table(broken, "2026-09")
            frame.drop(index=range(96, 192)).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                prepare(path)

    def test_strict_sensitivity_design(self):
        config = validate_config({"experiments": [{"name": "rte", "kind": "one_at_a_time",
                                                  "overrides": {"round_trip_efficiency": .81}}]})
        cases = list(experiment_configs(config))
        self.assertAlmostEqual(cases[1][2]["battery"]["eta_charge"], .9)
        config["experiments"][0]["overrides"]["sale_fee_eur_mwh"] = 3
        with self.assertRaises(ValueError):
            list(experiment_configs(config))
        for invalid in ({"scenario_count": 1}, {"typo": 1}, {"volatility_scale": float("nan")},
                        {"battery": {"purchase_fee_eur_mwh": -1}}):
            with self.assertRaises(ValueError):
                validate_config(invalid)

    def test_sensitivity_reoptimizes_and_report_renders(self):
        inputs = [("2026-10-01", np.array([[0., 100.], [10., 90.]]), np.array([0., 100.]))]
        metadata = {"month": "2026-10", "skipped_days": [], "model_training_before": "2026-10-01",
                    "calibration_month": "2026-09", "scenario_count": 2}
        config = validate_config({"scenario_count": 2, "battery": {"eta_charge": 1., "eta_discharge": 1.},
            "experiments": [{"name": "high_cost", "kind": "one_at_a_time", "overrides": {"degradation_eur_mwh_discharged": 1000}}]})
        with patch("scripts.run_commercial_backtest.prepare", return_value=pd.DataFrame()), \
             patch("scripts.run_commercial_backtest.build_month", return_value=(inputs, metadata)) as build:
            cases = run_experiments("unused.csv", ["2026-10"], config, progress=lambda *a, **k: None)
        self.assertEqual(build.call_count, 1)
        self.assertGreater(cases[0]["comparison"]["risk_neutral"]["net_profit_eur"], 0)
        self.assertAlmostEqual(cases[1]["comparison"]["risk_neutral"]["discharge_throughput_mwh"], 0)
        self.assertIsNone(cases[0]["walk_forward"])
        with tempfile.TemporaryDirectory() as directory:
            render_report({"experiments": cases, "provenance": {"source": "synthetic unit fixture"}}, directory)
            self.assertTrue((Path(directory) / "drawdown.svg").exists())
            self.assertIn("Walk-forward selection pending", (Path(directory) / "report.html").read_text())
            write_pending_report(Path(directory) / "pending")
            self.assertFalse((Path(directory) / "pending" / "daily.svg").exists())

    def test_daily_order_and_cost_configuration_mismatch(self):
        jan, feb = report("2026-01"), report("2026-02")
        feb["daily"] = [{**feb["daily"][0], "day": "2026-02-02"}, feb["daily"][0]]
        result = evaluate_months([jan, feb], require_complete=False)
        self.assertEqual(result["monthly"][0]["daily"][0]["day"], "2026-02-01")
        feb["battery"]["purchase_fee_eur_mwh"] = 1
        with self.assertRaisesRegex(ValueError, "configurations"):
            evaluate_months([jan, feb], require_complete=False)

    def test_report_training_cutoffs_are_enforced(self):
        for field in ("model_training_before", "calibration_model_training_before", "residual_folds_before"):
            jan, feb = report("2026-01"), report("2026-02")
            feb[field] = "2026-03-01"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "cutoff"):
                evaluate_months([jan, feb], require_complete=False)
        jan, feb = report("2026-01"), report("2026-02")
        for monthly in (jan, feb):
            monthly["battery"].update(initial_mwh=0, terminal_mwh=1)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            evaluate_months([jan, feb], require_complete=False)

    def test_full_calendar_walk_forward_with_accounting(self):
        from copy import deepcopy
        inputs = [("2026-01-01", np.array([[0., 100.], [10., 90.]]), np.array([0., 100.]))]
        first = evaluate_inputs(inputs, {"month": "2026-01", "skipped_days": []}, Battery(2, 1, 1, 1, 1))
        second = deepcopy(first)
        second["month"] = "2026-02"
        for monthly, count in ((first, 31), (second, 28)):
            daily = monthly["daily"][0]
            monthly["daily"] = [{**deepcopy(daily), "day": f"{monthly['month']}-{day:02d}"} for day in range(1, count + 1)]
        result = compare_reports([first, second], validate_config({}))
        self.assertEqual(result["walk_forward"]["evaluated_months"], 1)
        self.assertEqual(result["comparison"]["risk_neutral"]["days"], 28)
        self.assertAlmostEqual(result["comparison"]["risk_neutral"]["net_profit_eur"], 700)

    def test_saved_output_audit_detects_tampering(self):
        import hashlib
        from scripts.audit_commercial_results import audit_results
        config = validate_config({"scenario_count": 2})
        prices = np.array([0., 100.])
        monthly = evaluate_inputs([("2026-10-01", np.array([prices, prices]), prices)],
                                  {"month": "2026-10"}, Battery(**config["battery"]))
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic.csv"
            pd.DataFrame({"timestamp_utc": pd.date_range("2026-10-01", periods=2, freq="15min", tz="Europe/Berlin"),
                          "price_eur_mwh": prices}).to_csv(source, index=False)
            bundle = {"provenance": {"history_sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                      "experiments": [{"config": config, "monthly": [monthly]}]}
            self.assertEqual(audit_results(bundle, source)["schedules_checked"], 7)
            monthly["daily"][0]["accounting"]["0.0"]["net_profit_eur"] += 10
            with self.assertRaises(AssertionError):
                audit_results(bundle, source)
