"""Run sequential monthly battery evaluation with a fixed historical CSV.

Each month's model training and calibration uses strictly earlier delivery
dates. The first evaluated month is calibration-only for risk-weight selection.
"""
import argparse
import json
from datetime import date
from pathlib import Path

from battery_monthly_scenarios import month_bounds, run
from battery_walk_forward import evaluate_months
from battery_optimization import Battery
from battery_uncertainty import paired_profit_bootstrap, month_block_profit_bootstrap
from src.battery_validation import completed_month


def months_between(first, last):
    start, end = month_bounds(first)[0], month_bounds(last)[0]
    if start > end:
        raise ValueError("First month must not follow last month")
    months = []
    current = start
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        current = month_bounds(current.strftime("%Y-%m"))[1]
    return months


def validate_completed_months(first, last, *, today=None):
    """Reject evaluations that include a not-yet-completed calendar month."""
    months = months_between(first, last)
    completed_month(months[-1], today)
    return months


def main():
    parser = argparse.ArgumentParser(prog="run_battery_walk_forward.py", description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--first-month", default="2026-10")
    parser.add_argument("--last-month", required=True)
    parser.add_argument("--output-dir", default="output/rolling")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--lookback-months", type=int)
    parser.add_argument("--config", help="Commercial JSON assumptions; defaults preserve zero costs")
    args = parser.parse_args()
    months = validate_completed_months(args.first_month, args.last_month)
    if len(months) < 2:
        raise ValueError("At least two completed months are needed for walk-forward selection")
    from src.battery_config import load_config
    config = load_config(args.config)
    seed = config["seed"] if args.seed is None else args.seed
    battery = Battery(**config["battery"])
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    for month in months:
        report = run(args.history, month, battery, seed=seed, alpha=config["alpha"],
                     scenario_count=config["scenario_count"], volatility_scale=config["volatility_scale"])
        (output / f"monthly_{month}.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        reports.append(report)
        print(f"{month}: {len(report['daily'])} eligible days", flush=True)
    evaluation = evaluate_months(reports, lookback_months=args.lookback_months or config["lookback_months"],
        selection_rule=config["selection_rule"], downside_penalty=config["downside_penalty"])
    evaluation["uncertainty"] = paired_profit_bootstrap(
        [row for month in evaluation["monthly"] for row in month["daily"]],
        seed=seed)
    evaluation["month_block_uncertainty"] = month_block_profit_bootstrap(
        [row for month in evaluation["monthly"] for row in month["daily"]],
        seed=seed)
    (output / "walk_forward.json").write_text(
        json.dumps(evaluation, indent=2), encoding="utf-8")
    print(f"Walk-forward evaluated {evaluation['evaluated_months']} months")


if __name__ == "__main__":
    main()
