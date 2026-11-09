"""October 2026 multi-day benchmark; illustrative daily-cyclic battery.

Each local delivery day is optimized separately with initial=terminal energy.
This is NOT an interday SOC-carryover strategy. The DST day (100 slots)
is explicitly excluded because the scenario generator requires 96 slots.
Scenarios are provisional; tail-risk conclusions are not validated.
"""
import argparse
import json
from datetime import date
from pathlib import Path
import numpy as np
from scenarios import (prepare, past_residual_days, september_diagnostic,
                       fit_quantiles, predict, sample_scenarios)
from battery_optimization import Battery, deterministic, stochastic, perfect_foresight
from battery_comparison import realized_profit


def summarize(profits, alpha):
    x = np.asarray(profits, dtype=float)
    loss = -x
    threshold = float(np.quantile(loss, alpha))
    return {
        "days": len(x),
        "total_profit_eur": float(x.sum()),
        "mean_daily_profit_eur": float(x.mean()),
        "median_daily_profit_eur": float(np.median(x)),
        "min_daily_profit_eur": float(x.min()),
        "std_daily_profit_eur": float(x.std()),
        "negative_profit_days": int((x < 0).sum()),
        "empirical_var_loss_eur": threshold,
        "empirical_cvar_loss_eur": float(loss[loss >= threshold].mean()),
    }


def run(history_csv, battery, *, risk_weight=1.0, alpha=.95):
    table = prepare(history_csv)
    cutoff = date(2026, 10, 1)
    train = table[table["day"] < cutoff]
    october = table[(table["day"] >= cutoff) &
                    (table["day"] <= date(2026, 10, 31))]
    residuals, gap, _, _, past_scores = past_residual_days(train)
    _, _, _, _, _, final_gap, factor = september_diagnostic(
        train, residuals, gap, past_scores)
    models = fit_quantiles(train)

    daily = []
    skipped = []
    for day, rows in october.groupby("day", sort=True):
        if len(rows) != 96:
            skipped.append({"day": str(day), "intervals": len(rows),
                            "reason": "scenario generator supports 96 slots only"})
            continue
        lower, median, upper = predict(models, rows)
        paths = sample_scenarios(median, lower - final_gap,
                                 upper + final_gap, residuals,
                                 seed=42 + len(daily))
        paths = median + factor * (paths - median)
        actual = rows["price_eur_mwh"].to_numpy(dtype=float)
        results = {
            "deterministic": deterministic(paths, battery),
            "stochastic_cvar": stochastic(paths, battery,
                                          risk_weight=risk_weight, alpha=alpha),
            "perfect_foresight": perfect_foresight(actual, battery),
        }
        record = {"day": str(day), "intervals": len(rows)}
        for name, schedule in results.items():
            record[name] = realized_profit(
                schedule, actual, variable_cost=battery.variable_cost_eur_mwh)
        daily.append(record)

    if not daily:
        raise ValueError("No 96-interval days available")
    names = ("deterministic", "stochastic_cvar", "perfect_foresight")
    return {
        "evaluation_month": "2026-10",
        "risk_quality_validated": False,
        "battery_parameters_verified": False,
        "soc_policy": "daily_cyclic_initial_equals_terminal; no interday carryover",
        "cvar_alpha": alpha,
        "risk_weight": risk_weight,
        "battery": vars(battery),
        "skipped_days": skipped,
        "summary": {name: summarize([r[name] for r in daily], alpha)
                    for name in names},
        "daily": daily,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", default="output/battery_october_benchmark.json")
    parser.add_argument("--capacity-mwh", type=float, required=True)
    parser.add_argument("--power-mw", type=float, required=True)
    parser.add_argument("--eta-charge", type=float, default=.95)
    parser.add_argument("--eta-discharge", type=float, default=.95)
    parser.add_argument("--initial-mwh", type=float, required=True)
    parser.add_argument("--risk-weight", type=float, default=1.0)
    parser.add_argument("--alpha", type=float, default=.95)
    args = parser.parse_args()
    battery = Battery(args.capacity_mwh, args.power_mw,
                      args.eta_charge, args.eta_discharge, args.initial_mwh)
    report = run(args.history, battery, risk_weight=args.risk_weight, alpha=args.alpha)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Evaluated {len(report['daily'])} days; skipped {report['skipped_days']}")
    for name, stats in report["summary"].items():
        print(f"{name}: total EUR {stats['total_profit_eur']:.2f}; "
              f"mean/day EUR {stats['mean_daily_profit_eur']:.2f}; "
              f"empirical CVaR loss EUR {stats['empirical_cvar_loss_eur']:.2f}")
    print("WARNING: illustrative battery; scenario tail risk not validated.")


if __name__ == "__main__":
    main()
