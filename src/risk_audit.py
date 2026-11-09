"""Audit 50 price scenarios against real October 2026 prices.

This module assesses price scenarios, not battery profit or CVaR.
"""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse the project scenario generation functions for consistent evaluation.
from scenarios import (prepare, fit_quantiles, predict, past_residual_days,
                       september_diagnostic, sample_scenarios)


def serial_correlation(values):
    """Return adjacent 15-minute price autocorrelation within a day."""

    # Correlation is undefined for constant-price paths.
    if np.std(values[:-1]) == 0 or np.std(values[1:]) == 0:
        return float("nan")
    return float(np.corrcoef(values[:-1], values[1:])[0, 1])


def risk_metrics(actual, paths, historical_low, historical_high):
    """Compare actual prices with scenario distributions and upper/lower tails.

    actual: (days, 96 intervals); paths: (days, 50 scenarios, 96 intervals).
    """

    # Validate array shapes without discarding evaluation prices.
    if actual.ndim != 2 or paths.ndim != 3:
        raise ValueError("Invalid price/scenario array dimensions.")
    if actual.shape[0] != paths.shape[0] or actual.shape[1] != paths.shape[2]:
        raise ValueError("Realized and scenario arrays have mismatched days or intervals.")
    if not np.isfinite(actual).all() or not np.isfinite(paths).all():
        raise ValueError("Non-finite actual or scenario prices.")

    # Calculate 10th and 90th percentiles across the 50 scenarios.
    p10, p90 = np.quantile(paths, [0.1, 0.9], axis=1)
    below = float(np.mean(actual < p10))
    above = float(np.mean(actual > p90))

    # Extreme thresholds are calculated from pre-October training data only.
    # Compare negative prices and exceedances of training 5th/95th percentiles.
    extreme_rates = {
        "negative_actual": float(np.mean(actual < 0)),
        # Keep explicit counts to avoid rounding rare events to zero.
        "negative_actual_count": int(np.sum(actual < 0)),
        "negative_scenarios": float(np.mean(paths < 0)),
        "below_training_p05_actual": float(np.mean(actual < historical_low)),
        "below_training_p05_scenarios": float(np.mean(paths < historical_low)),
        "above_training_p95_actual": float(np.mean(actual > historical_high)),
        "above_training_p95_scenarios": float(np.mean(paths > historical_high)),
    }

    # Compare daily peak-to-trough price ranges.
    real_range = np.ptp(actual, axis=1)
    scenario_range = np.ptp(paths, axis=2)
    high_range = np.quantile(scenario_range, 0.9, axis=1)

    # Evaluate daily minima and maxima, not only individual intervals.
    real_min, real_max = actual.min(axis=1), actual.max(axis=1)
    predicted_min = paths.min(axis=2)
    predicted_max = paths.max(axis=2)
    low_min = np.quantile(predicted_min, 0.1, axis=1)
    high_max = np.quantile(predicted_max, 0.9, axis=1)

    # Compare adjacent-interval autocorrelation.
    real_corr = [serial_correlation(day) for day in actual]
    path_corr = [serial_correlation(path) for day in paths for path in day]

    # These are price diagnostics, not battery schedule profit/loss metrics.
    return {
        "days_evaluated": int(len(actual)),
        "intervals_evaluated": int(actual.size),
        "scenarios_per_day": int(paths.shape[1]),
        "training_p05_eur_mwh": float(historical_low),
        "training_p95_eur_mwh": float(historical_high),
        "below_scenario_p10_rate": below,     # Nominal target about 10%.
        "above_scenario_p90_rate": above,     # Nominal target about 10%.
        "scenario_p10_p90_coverage": 1.0 - below - above,  # Nominal target 80%.
        "extreme_interval_rates": extreme_rates,
        "mean_actual_daily_range_eur_mwh": float(real_range.mean()),
        "mean_scenario_daily_range_eur_mwh": float(scenario_range.mean()),
        "actual_daily_range_above_scenario_p90_rate":
            float(np.mean(real_range > high_range)),
        "actual_daily_min_below_scenario_min_p10_rate":
            float(np.mean(real_min < low_min)),
        "actual_daily_max_above_scenario_max_p90_rate":
            float(np.mean(real_max > high_max)),
        "mean_actual_adjacent_quarterhour_correlation":
            float(np.nanmean(real_corr)),
        "mean_scenario_adjacent_quarterhour_correlation":
            float(np.nanmean(path_corr)),
        "risk_ready": False,  # Price diagnostics do not validate battery CVaR.
        "notes": [
            "October actuals were read only after each day's scenarios were generated.",
            "October 25 has 100 intervals and is excluded because it is unsupported.",
            "Only about 2-3 of 50 paths fall in the 95% loss tail.",
            "Price diagnostics alone cannot validate the loss tail of a battery schedule.",
        ],
    }


def main():
    """Build October scenarios from saved history and write a risk report."""

    import argparse
    parser = argparse.ArgumentParser(description="Evaluate price tails and daily volatility")
    parser.add_argument("--input", required=True, help="DE-LU historical CSV file")
    parser.add_argument("--output", default="output/risk_report.json")
    args = parser.parse_args()

    table = prepare(args.input)
    train = table[table["day"] < date(2026, 10, 1)]
    october = table[(table["day"] >= date(2026, 10, 1)) &
                    (table["day"] <= date(2026, 10, 31))]

    # Determine all parameters using pre-October training data.
    residuals, gap, _, _, past_scores = past_residual_days(train)
    _, _, _, _, _, final_gap, factor = september_diagnostic(
        train, residuals, gap, past_scores)
    models = fit_quantiles(train)

    # Calculate extreme thresholds from pre-October prices only.
    prices_before_october = train["price_eur_mwh"].to_numpy()
    p05, p95 = np.quantile(prices_before_october, [0.05, 0.95])

    actual_days, scenario_days = [], []
    for day, rows in october.groupby("day", sort=True):
        # Skip the unsupported 100-interval autumn DST day.
        if len(rows) != 96:
            print(f"Skipped {day} ({len(rows)} intervals) in scenario evaluation.")
            continue

        # Predict and sample without using target-day realized prices.
        low, middle, high = predict(models, rows)
        paths = sample_scenarios(
            middle, low - final_gap, high + final_gap,
            residuals, seed=42 + len(actual_days))
        paths = middle + factor * (paths - middle)
        scenario_days.append(paths)

        # Read actual prices only after generating scenarios for evaluation.
        actual_days.append(rows["price_eur_mwh"].to_numpy())

    report = risk_metrics(np.array(actual_days), np.array(scenario_days), p05, p95)
    report["training_last_day"] = "2026-09-30"
    report["evaluation_month"] = "2026-10"

    # Write a reproducible research report.
    filename = Path(args.output)
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Days/intervals: {report['days_evaluated']} / {report['intervals_evaluated']}")
    print(f"Scenario 10th-90th percentile coverage: {report['scenario_p10_p90_coverage']:.3f}")
    print(f"Below/above scenario bounds: {report['below_scenario_p10_rate']:.3f} / "
          f"{report['above_scenario_p90_rate']:.3f}")
    print(f"Mean actual/scenario daily range (EUR/MWh): "
          f"{report['mean_actual_daily_range_eur_mwh']:.1f} / "
          f"{report['mean_scenario_daily_range_eur_mwh']:.1f}")
    print("Actual negative prices: "
          f"{report['extreme_interval_rates']['negative_actual_count']} intervals out of "
          f"{report['intervals_evaluated']} intervals")
    print("Actual/scenario negative-price rate: "
          f"{100*report['extreme_interval_rates']['negative_actual']:.3f}% / "
          f"{100*report['extreme_interval_rates']['negative_scenarios']:.2f}%")
    print(f"Saved report: {filename}")
    print("Warning: price diagnostics do not validate battery profit/loss or CVaR.")


if __name__ == "__main__":
    main()
