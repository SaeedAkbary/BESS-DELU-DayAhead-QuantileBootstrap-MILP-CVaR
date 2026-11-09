"""Sensitivity of October battery dispatch to CVaR risk aversion.

Scenarios are generated once per day and reused for every risk weight.
Daily SOC is cyclic; battery parameters are illustrative, not site-verified.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
from scenarios import (prepare, past_residual_days, september_diagnostic,
                       fit_quantiles, predict, sample_scenarios)
from battery_optimization import Battery, stochastic, perfect_foresight
from battery_comparison import realized_profit
from battery_october_benchmark import summarize

WEIGHTS = (0.0, 0.25, 0.5, 1.0, 2.0)


def run(history_csv, battery, alpha=0.95):
    """Fit before October; compare fixed day-ahead schedules on held-out prices."""
    table = prepare(history_csv)
    train = table[table["day"] < date(2026, 10, 1)]
    october = table[(table["day"] >= date(2026, 10, 1)) &
                    (table["day"] <= date(2026, 10, 31))]
    residuals, gap, _, _, scores = past_residual_days(train)
    _, _, _, _, _, final_gap, factor = september_diagnostic(
        train, residuals, gap, scores)
    models = fit_quantiles(train)

    daily, skipped = [], []
    for day, rows in october.groupby("day", sort=True):
        if len(rows) != 96:
            skipped.append({"day": str(day), "intervals": len(rows)})
            continue
        low, mid, high = predict(models, rows)
        paths = sample_scenarios(mid, low - final_gap, high + final_gap,
                                 residuals, seed=42 + len(daily))
        paths = mid + factor * (paths - mid)
        actual = rows["price_eur_mwh"].to_numpy(dtype=float)

        # Use the same scenario paths for all five risk settings.
        row = {"day": str(day)}
        for weight in WEIGHTS:
            dispatch = stochastic(paths, battery, risk_weight=weight, alpha=alpha)
            row[str(weight)] = realized_profit(
                dispatch, actual, variable_cost=battery.variable_cost_eur_mwh)
        oracle = perfect_foresight(actual, battery)
        row["oracle"] = realized_profit(
            oracle, actual, variable_cost=battery.variable_cost_eur_mwh)
        daily.append(row)

    if not daily:
        raise ValueError("No eligible days")
    return {
        "month": "2026-10", "alpha": alpha, "battery": vars(battery),
        "battery_verified": False, "scenario_risk_validated": False,
        "daily_cyclic_soc": True, "skipped_days": skipped,
        "summary": {str(w): summarize([r[str(w)] for r in daily], alpha)
                    for w in WEIGHTS},
        "oracle": summarize([r["oracle"] for r in daily], alpha),
        "daily": daily,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--history", required=True)
    p.add_argument("--output", default="output/battery_risk_sensitivity.json")
    a = p.parse_args()
    # Illustrative battery; NOT Bollingstedt plant specifications.
    battery = Battery(capacity_mwh=2, power_mw=1, eta_charge=.95,
                      eta_discharge=.95, initial_mwh=1,
                      variable_cost_eur_mwh=0)
    report = run(a.history, battery)
    dest = Path(a.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Evaluated {len(report['daily'])} days; skipped: {report['skipped_days']}")
    for w, stats in report["summary"].items():
        print(f"weight={w}: total EUR {stats['total_profit_eur']:.2f}; "
              f"mean EUR/day {stats['mean_daily_profit_eur']:.2f}; "
              f"empirical CVaR loss EUR {stats['empirical_cvar_loss_eur']:.2f}")
    print("WARNING: exploratory October results, illustrative battery and provisional scenarios")


if __name__ == "__main__":
    main()
