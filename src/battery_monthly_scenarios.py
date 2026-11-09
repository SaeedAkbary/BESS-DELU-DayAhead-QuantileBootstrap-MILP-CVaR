"""Leakage-controlled monthly scenario inputs for rolling battery evaluation.

This is an alternative to the frozen October benchmark, not a replacement.
Historical residual templates use the fixed February-August 2026 folds in
scenarios.py. The preceding calendar month calibrates an additive interval
gap; quantile models for the target month train only on earlier dates.
No target-month realized prices are used to construct scenarios.

Supported target months start in October 2026. The procedure deliberately
uses no September-tuned scenario inflation factor; calibration methodology
must be validated independently before drawing tail-risk conclusions.
"""
import argparse
import calendar
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from battery_scenario_diagnostics import scenario_diagnostics

from scenarios import (
    prepare, past_residual_days, fit_quantiles, predict,
    sample_scenarios, calibration_gap,
)


def month_bounds(month):
    """Return inclusive start and exclusive end of a YYYY-MM month."""
    if len(month) != 7 or month[4] != "-":
        raise ValueError("Expected YYYY-MM")
    start = date.fromisoformat(month + "-01")
    end = date(start.year + (start.month == 12),
               start.month % 12 + 1, 1)
    return start, end


def build_month(table, month, *, scenario_count=50, seed=42):
    """Generate scenarios before inspecting each target day's realized prices.

    Returns a list of (day, scenarios, actual_prices) tuples and metadata.
    Actual prices are included only for downstream realized-profit scoring;
    they are not accessed until scenario construction is complete.
    """
    start, end = month_bounds(month)
    if start < date(2026, 10, 1):
        raise ValueError("Historical residual folds require target >= 2026-10")
    if scenario_count < 1:
        raise ValueError("scenario_count must be positive")

    calibration_end = start
    calibration_start = start.replace(day=1) - timedelta(days=1)
    calibration_start = calibration_start.replace(day=1)

    prior = table[table["day"] < calibration_start]
    calibration = table[(table["day"] >= calibration_start) &
                        (table["day"] < calibration_end)]
    training = table[table["day"] < start]
    evaluation = table[(table["day"] >= start) & (table["day"] < end)]
    if calibration.empty or evaluation.empty:
        raise ValueError("Missing calibration or evaluation prices")

    # Calibration forecasts are fit strictly before the calibration month.
    calibration_models = fit_quantiles(prior)
    low, _, high = predict(calibration_models, calibration)
    gap = calibration_gap(calibration["price_eur_mwh"].to_numpy(),
                          low, high)
    # Residual folds remain anchored to historical February-August 2026.
    historical = table[table["day"] < date(2026, 9, 1)]
    residuals, _, _, _, _ = past_residual_days(historical)
    models = fit_quantiles(training)

    daily, skipped = [], []
    for day, rows in evaluation.groupby("day", sort=True):
        if len(rows) != 96:
            skipped.append({"day": str(day), "intervals": len(rows),
                            "reason": "only 96-interval days supported"})
            continue
        lower, median, upper = predict(models, rows)
        paths = sample_scenarios(median, lower - gap, upper + gap,
                                 residuals, seed=seed + len(daily),
                                 count=scenario_count)
        # Read actual prices only after scenario paths are fixed.
        actual = rows["price_eur_mwh"].to_numpy(dtype=float)
        daily.append((str(day), paths, actual))
    if not daily:
        raise ValueError("No eligible 96-interval evaluation days")
    return daily, {
        "month": month,
        "calibration_month": calibration_start.strftime("%Y-%m"),
        "model_training_before": start.isoformat(),
        "calibration_model_training_before": calibration_start.isoformat(),
        "residual_folds_before": "2026-09-01",
        "calibration_gap_eur_mwh": float(gap),
        "scenario_count": scenario_count,
        "seed": seed,
        "skipped_days": skipped,
        "scenario_risk_validated": False,
    }


def run(history_csv, month, battery, *, alpha=.95, seed=42):
    """Score all CVaR weights against identical generated monthly scenarios."""
    from battery_risk_sensitivity import WEIGHTS
    from battery_optimization import stochastic, perfect_foresight
    from battery_comparison import realized_profit
    from battery_october_benchmark import summarize

    daily_inputs, metadata = build_month(prepare(history_csv), month, seed=seed)
    diagnostics = scenario_diagnostics(daily_inputs)
    daily = []
    for day, paths, actual in daily_inputs:
        row = {"day": day, "dispatch": {}}
        for weight in WEIGHTS:
            dispatch = stochastic(paths, battery, risk_weight=weight, alpha=alpha)
            row[str(weight)] = realized_profit(
                dispatch, actual, variable_cost=battery.variable_cost_eur_mwh)
            row["dispatch"][str(weight)] = {
                "charge_mw": dispatch["charge_mw"],
                "discharge_mw": dispatch["discharge_mw"],
                "energy_mwh": dispatch["energy_mwh"],
            }
        oracle = perfect_foresight(actual, battery)
        row["oracle"] = realized_profit(
            oracle, actual, variable_cost=battery.variable_cost_eur_mwh)
        daily.append(row)
    return {
        **metadata, "alpha": alpha, "battery": vars(battery),
        "scenario_diagnostics": diagnostics,
        "battery_verified": False, "daily_cyclic_soc": True,
        "summary": {str(w): summarize([r[str(w)] for r in daily], alpha)
                    for w in WEIGHTS},
        "oracle": summarize([r["oracle"] for r in daily], alpha),
        "daily": daily,
    }


def main():
    from battery_optimization import Battery
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM, >= 2026-10")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    battery = Battery(capacity_mwh=2, power_mw=1, eta_charge=.95,
                      eta_discharge=.95, initial_mwh=1)
    result = run(args.history, args.month, battery, seed=args.seed)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{args.month}: {len(result['daily'])} days; "
          f"calibrated using {result['calibration_month']}")


if __name__ == "__main__":
    main()
