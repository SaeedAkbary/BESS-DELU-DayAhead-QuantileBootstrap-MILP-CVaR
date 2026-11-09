"""Evaluate day-ahead schedules from an existing scenario CSV.

Use the scenario CSV produced by scenarios.py (50 scenario columns). The
realized price CSV is used *only after* optimization to score fixed schedules.
Battery parameters are illustrative, NOT verified Bollingstedt specifications.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from battery_optimization import Battery, deterministic, stochastic, perfect_foresight


def realized_profit(schedule, actual, dt_hours=0.25, variable_cost=0):
    charge = np.asarray(schedule["charge_mw"], dtype=float)
    discharge = np.asarray(schedule["discharge_mw"], dtype=float)
    actual = np.asarray(actual, dtype=float)
    if actual.shape != charge.shape or charge.shape != discharge.shape:
        raise ValueError("Realized prices and dispatch must have equal length")
    return float(dt_hours * np.sum(actual * (discharge - charge)
                   - variable_cost * (charge + discharge)))


def evaluate(scenario_csv, history_csv, battery, *, risk_weight=1.0, alpha=.95):
    scenario_frame = pd.read_csv(scenario_csv)
    columns = sorted(c for c in scenario_frame if c.startswith("scenario_"))
    if not columns:
        raise ValueError("No scenario_XX columns found")
    scenarios = scenario_frame[columns].to_numpy(dtype=float).T
    scenario_times = pd.to_datetime(scenario_frame["timestamp_utc"], utc=True)
    if scenario_times.isna().any() or scenario_times.duplicated().any():
        raise ValueError("Scenario timestamps must be unique and valid")
    if len(scenario_times) > 1 and not (scenario_times.diff().iloc[1:] == pd.Timedelta(minutes=15)).all():
        raise ValueError("Scenario timestamps must be 15 minutes apart")
    history = pd.read_csv(history_csv)
    history["timestamp_utc"] = pd.to_datetime(history["timestamp_utc"], utc=True)
    if history["timestamp_utc"].duplicated().any():
        raise ValueError("Duplicate historical timestamps")
    actual = history.set_index("timestamp_utc")["price_eur_mwh"].reindex(scenario_times)
    if actual.isna().any():
        raise ValueError("Missing realized prices for scenario timestamps")
    realized = actual.to_numpy(dtype=float)
    if not np.isfinite(scenarios).all() or not np.isfinite(realized).all():
        raise ValueError("Non-finite prices")

    results = {
        "deterministic": deterministic(scenarios, battery),
        "stochastic_cvar": stochastic(scenarios, battery, risk_weight=risk_weight, alpha=alpha),
        "perfect_foresight": perfect_foresight(realized, battery),
    }
    summary = {}
    for name, schedule in results.items():
        summary[name] = {
            "realized_profit_eur": realized_profit(schedule, realized,
                variable_cost=battery.variable_cost_eur_mwh),
            "expected_scenario_profit_eur": schedule["expected_profit_eur"],
            "charge_mw": schedule["charge_mw"],
            "discharge_mw": schedule["discharge_mw"],
            "energy_mwh": schedule["energy_mwh"],
        }
    return {
        "intervals": len(scenario_times),
        "scenario_count": len(scenarios),
        "battery_parameters_are_illustrative": True,
        "scenario_risk_quality_validated": False,
        "results": summary,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output", default="output/battery_comparison.json")
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
    report = evaluate(args.scenarios, args.history, battery,
                      risk_weight=args.risk_weight, alpha=args.alpha)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for method, row in report["results"].items():
        print(f"{method}: realized profit EUR {row['realized_profit_eur']:.2f}")
    print("Illustrative battery; CVaR scenarios not risk-validated.")


if __name__ == "__main__":
    main()
