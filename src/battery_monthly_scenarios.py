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
from src.battery_validation import validate_month_table
from src.battery_economics import account_dispatch
from src.battery_metrics import summarize_net

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


def build_month(table, month, *, scenario_count=50, seed=42, today=None):
    """Generate scenarios before inspecting each target day's realized prices.

    Returns a list of (day, scenarios, actual_prices) tuples and metadata.
    Actual prices are included only for downstream realized-profit scoring;
    they are not accessed until scenario construction is complete.
    """
    start, end = month_bounds(month)
    if start < date(2026, 10, 1):
        raise ValueError("Historical residual folds require target >= 2026-10")
    if isinstance(scenario_count, bool) or not isinstance(scenario_count, int) or scenario_count < 2:
        raise ValueError("scenario_count must be an integer >= 2")
    validate_month_table(table, month, today)
    table = table.sort_values("timestamp_utc").copy()
    if not (table["day"] == table["timestamp_utc"].dt.tz_convert("Europe/Berlin").dt.date).all():
        raise ValueError("Delivery dates must match Berlin timestamps")

    calibration_end = start
    calibration_start = start.replace(day=1) - timedelta(days=1)
    calibration_start = calibration_start.replace(day=1)
    validate_month_table(table, calibration_start.strftime("%Y-%m"), today)

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
    past_volatility = training.groupby("day")["price_eur_mwh"].std(ddof=0)
    low_vol, high_vol = np.quantile(past_volatility, [.25, .75])
    regimes = {day: ("low" if np.std(actual) <= low_vol else
                     "high" if np.std(actual) > high_vol else "middle")
               for day, _, actual in daily}
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
        "calendar_complete": True,
        "publication_vintages_verified": False,
        "volatility_regimes": regimes,
        "volatility_regime_thresholds_eur_mwh": [float(low_vol), float(high_vol)],
        "volatility_regime_definition": "Ex-post target daily price std versus prior-month-training q25/q75; reporting only, not dispatch inputs",
        "evaluation_role": "development" if month == "2026-10" else "chronological; untouched status requires research log",
    }


def run(history_csv, month, battery, *, alpha=.95, seed=42, scenario_count=50,
        volatility_scale=1.0, today=None):
    """Score all CVaR weights against identical generated monthly scenarios."""
    battery.validate()
    if battery.terminal_mwh not in (None, battery.initial_mwh):
        raise ValueError("Monthly comparison requires daily cyclic SOC for a feasible zero baseline")
    if not np.isfinite(volatility_scale) or volatility_scale <= 0:
        raise ValueError("volatility_scale must be finite and positive")
    daily_inputs, metadata = build_month(prepare(history_csv), month, seed=seed,
        scenario_count=scenario_count, today=today)
    # Prespecified uncertainty stress about each forecast's mean; actual prices unchanged.
    daily_inputs = [(day, paths if volatility_scale == 1 else paths.mean(axis=0) + volatility_scale * (paths - paths.mean(axis=0)), actual)
                    for day, paths, actual in daily_inputs]
    metadata["volatility_scale"] = volatility_scale
    return evaluate_inputs(daily_inputs, metadata, battery, alpha=alpha)


def evaluate_inputs(daily_inputs, metadata, battery, *, alpha=.95):
    """Re-optimize every policy on common fixed scenarios (also used by sensitivity)."""
    from battery_risk_sensitivity import WEIGHTS
    from battery_optimization import stochastic, perfect_foresight
    from battery_comparison import realized_profit
    from battery_october_benchmark import summarize
    battery.validate()
    if battery.terminal_mwh not in (None, battery.initial_mwh):
        raise ValueError("Daily cyclic SOC is required for the zero-dispatch baseline")
    diagnostics = scenario_diagnostics(daily_inputs)
    daily = []
    for day, paths, actual in daily_inputs:
        row = {"day": day, "dispatch": {}, "accounting": {}, "scenario_risk": {}, "scenario_expected_net_profit_eur": {}}
        for weight in WEIGHTS:
            dispatch = stochastic(paths, battery, risk_weight=weight, alpha=alpha)
            row[str(weight)] = realized_profit(
                dispatch, actual, battery=battery)
            row["dispatch"][str(weight)] = {
                "charge_mw": dispatch["charge_mw"],
                "discharge_mw": dispatch["discharge_mw"],
                "energy_mwh": dispatch["energy_mwh"],
            }
            row["accounting"][str(weight)] = account_dispatch(dispatch, actual, battery)
            row["scenario_risk"][str(weight)] = dispatch.get("scenario_cvar_loss_eur")
            row["scenario_expected_net_profit_eur"][str(weight)] = dispatch.get("expected_profit_eur")
        oracle = perfect_foresight(actual, battery)
        row["oracle"] = realized_profit(
            oracle, actual, battery=battery)
        row["dispatch"]["oracle"] = oracle
        row["accounting"]["oracle"] = account_dispatch(oracle, actual, battery)
        zero = {"charge_mw": [0.] * len(actual), "discharge_mw": [0.] * len(actual),
                "energy_mwh": [battery.initial_mwh] * (len(actual) + 1)}
        row["zero_dispatch"] = 0.0
        row["dispatch"]["zero_dispatch"] = zero
        row["accounting"]["zero_dispatch"] = account_dispatch(zero, actual, battery)
        daily.append(row)
    regimes = metadata.get("volatility_regimes", {})
    regime_summary = {regime: {w: summarize_net([r[w] for r in daily if regimes.get(r["day"]) == regime], alpha)
        for w in (*map(str, WEIGHTS), "oracle", "zero_dispatch")}
        for regime in ("low", "middle", "high") if any(regimes.get(r["day"]) == regime for r in daily)}
    return {
        **metadata, "alpha": alpha, "battery": vars(battery),
        "realized_volatility_regime_summary": regime_summary,
        "scenario_diagnostics": diagnostics,
        "battery_verified": False, "daily_cyclic_soc": True,
        "summary": {str(w): summarize([r[str(w)] for r in daily], alpha)
                    for w in WEIGHTS},
        "oracle": summarize([r["oracle"] for r in daily], alpha),
        "commercial_summary": {w: summarize_net([r[w] for r in daily], alpha,
            [r["accounting"][w] for r in daily]) for w in
            (*map(str, WEIGHTS), "oracle", "zero_dispatch")},
        "daily": daily,
    }


def main():
    from battery_optimization import Battery
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM, >= 2026-10")
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--config", help="Commercial JSON assumptions; defaults preserve zero costs")
    args = parser.parse_args()
    from src.battery_config import load_config
    config = load_config(args.config)
    battery = Battery(**config["battery"])
    result = run(args.history, args.month, battery, seed=config["seed"] if args.seed is None else args.seed, alpha=config["alpha"],
                 scenario_count=config["scenario_count"], volatility_scale=config["volatility_scale"])
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{args.month}: {len(result['daily'])} days; "
          f"calibrated using {result['calibration_month']}")


if __name__ == "__main__":
    main()
