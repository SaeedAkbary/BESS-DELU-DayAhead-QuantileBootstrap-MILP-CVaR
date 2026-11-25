"""Leakage-safe rolling risk-weight selection from precomputed monthly reports.

Each input monthly report must contain out-of-sample daily realized profits
for all risk weights. This module does NOT generate price scenarios or
establish that upstream forecasts are leakage-free. The first month is used
only for calibration; each subsequent month is evaluated with a weight
selected from strictly earlier months.
"""
import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path

from battery_chronological_holdout import WEIGHTS
from src.battery_metrics import summarize_net
from src.battery_validation import validate_report_calendar


def evaluate_months(reports, *, lookback_months=None, selection_rule="profit",
                    downside_penalty=0.0, require_complete=True, today=None):
    """Select lambda from earlier months, never the evaluation month."""
    if lookback_months is not None and lookback_months < 1:
        raise ValueError("lookback_months must be positive")
    if selection_rule not in ("profit", "net_downside"):
        raise ValueError("Unknown selection rule")
    if not math.isfinite(downside_penalty) or downside_penalty < 0:
        raise ValueError("Downside penalty must be finite and nonnegative")
    by_month = {}
    for report in reports:
        month = report["month"]
        if len(month) != 7 or month[4] != "-" or date.fromisoformat(month + "-01").strftime("%Y-%m") != month:
            raise ValueError(f"Invalid month: {month}")
        if month in by_month:
            raise ValueError(f"Duplicate month: {month}")
        rows = report["daily"]
        if not rows:
            raise ValueError(f"Empty month: {month}")
        if require_complete:
            validate_report_calendar(report, today)
        cutoff = date.fromisoformat(month + "-01")
        calibration_start = (cutoff - timedelta(days=1)).replace(day=1)
        for field, bound in (("model_training_before", cutoff),
                             ("calibration_model_training_before", calibration_start),
                             ("residual_folds_before", cutoff)):
            if field in report and date.fromisoformat(report[field]) > bound:
                raise ValueError(f"{field} violates the target-period information cutoff")
        if "calibration_month" in report and report["calibration_month"] != calibration_start.strftime("%Y-%m"):
            raise ValueError("Calibration month must immediately precede evaluation")
        battery = report.get("battery") or {}
        if battery.get("terminal_mwh") not in (None, battery.get("initial_mwh")):
            raise ValueError("Cyclic SOC is required for the zero-dispatch comparison")
        seen = set()
        for row in rows:
            day = date.fromisoformat(row["day"])
            if day.strftime("%Y-%m") != month or row["day"] in seen:
                raise ValueError(f"Invalid or duplicate daily date in {month}")
            seen.add(row["day"])
            for weight in (*WEIGHTS, "oracle"):
                if weight not in row:
                    raise ValueError(f"Missing {weight} on {day}")
                value = row[weight]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"Non-finite or non-numeric {weight} on {day}")
        by_month[month] = {**report, "daily": sorted(rows, key=lambda row: row["day"])}

    months = sorted(by_month)
    if len(months) < 2:
        raise ValueError("At least two months are required")
    for i in range(1, len(months)):
        previous = date.fromisoformat(months[i - 1] + "-01")
        expected = (previous.replace(day=28) + timedelta(days=4)).replace(day=1)
        if date.fromisoformat(months[i] + "-01") != expected:
            raise ValueError("Monthly reports must be consecutive for walk-forward evaluation")
    alphas = {by_month[m]["alpha"] for m in months}
    if len(alphas) != 1:
        raise ValueError("All months must use the same CVaR alpha")
    batteries = {json.dumps(by_month[m].get("battery"), sort_keys=True) for m in months}
    if len(batteries) != 1:
        raise ValueError("Battery configurations must match")
    alpha = alphas.pop()
    if not 0 < alpha < 1:
        raise ValueError("Invalid alpha")
    for field in ("scenario_count", "volatility_scale"):
        if len({r.get(field) for r in by_month.values()}) != 1:
            raise ValueError(f"Monthly {field} assumptions must match")
    outcomes = []
    for i, month in enumerate(months[1:], start=1):
        history = months[:i]
        if lookback_months is not None:
            history = history[-lookback_months:]
        training = [row for m in history for row in by_month[m]["daily"]]
        totals = {w: sum(row[w] for row in training) for w in WEIGHTS}
        scores = totals.copy()
        if selection_rule == "net_downside":
            scores = {}
            for w in WEIGHTS:
                stats = summarize_net([row[w] for row in training], alpha)
                scores[w] = stats["mean_daily_profit_eur"] - downside_penalty * max(0., stats["empirical_cvar_loss_eur"])
        chosen = max(WEIGHTS, key=lambda w: (scores[w], -float(w)))
        selection_cutoff = date.fromisoformat(month + "-01")
        if any(date.fromisoformat(row["day"]) >= selection_cutoff for row in training):
            raise ValueError("Risk-weight selection contains evaluation-month or future prices")
        evaluation = by_month[month]["daily"]
        def stats(key):
            accounting = ([row["accounting"][key] for row in evaluation]
                          if all("accounting" in row for row in evaluation) else None)
            return summarize_net([row[key] for row in evaluation], alpha, accounting)
        selected = stats(chosen)
        baseline = stats("0.0")
        outcomes.append({
            "evaluation_month": month,
            "selection_months": history,
            "selection_cutoff_exclusive": selection_cutoff.isoformat(),
            "selection_observation_count": len(training),
            "selection_rule": selection_rule,
            "downside_penalty": downside_penalty,
            "selection_scores": scores,
            "selected_lambda": float(chosen),
            "selection_profit_eur": totals,
            "days": len(evaluation),
            "selected": selected,
            "risk_neutral": baseline,
            "oracle": stats("oracle"),
            "zero_dispatch": summarize_net([0.] * len(evaluation), alpha),
            "skipped_days": by_month[month].get("skipped_days", []),
            "daily": [
                {"day": row["day"], "selected": row[chosen],
                 "risk_neutral": row["0.0"], "oracle": row["oracle"], "zero_dispatch": 0.,
                 "accounting": {name: row["accounting"][key] for name, key in
                    (("selected", chosen), ("risk_neutral", "0.0"), ("oracle", "oracle"),
                     ("zero_dispatch", "zero_dispatch"))} if "accounting" in row else None}
                for row in evaluation
            ],
        })
    daily = [row for outcome in outcomes for row in outcome["daily"]]
    return {
        "alpha": alpha,
        "battery": by_month[months[0]].get("battery"),
        "calibration_only_month": months[0],
        "lookback_months": lookback_months,
        "evaluated_months": len(outcomes),
        "monthly": outcomes,
        "aggregate": {
            strategy: summarize_net([row[strategy] for row in daily], alpha,
                [row["accounting"][strategy] for row in daily] if all(row["accounting"] for row in daily) else None)
            for strategy in ("selected", "risk_neutral", "oracle", "zero_dispatch")
        },
        "limitations": [
            "Upstream monthly scenarios and their temporal validity are not verified here",
            "Daily-cyclic battery and eligible-day exclusions are inherited from input reports",
            "Selector and downside penalty must be frozen before inspecting target outcomes",
            "Source publication vintages are not verified; chronology is not proof of tradability",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="Monthly risk sensitivity JSON files")
    parser.add_argument("--lookback-months", type=int)
    parser.add_argument("--selection-rule", choices=("profit", "net_downside"), default="profit")
    parser.add_argument("--downside-penalty", type=float, default=0.)
    parser.add_argument("--output", default="output/battery_walk_forward.json")
    args = parser.parse_args()
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
    result = evaluate_months(reports, lookback_months=args.lookback_months,
        selection_rule=args.selection_rule, downside_penalty=args.downside_penalty)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Evaluated {result['evaluated_months']} months")
    for month in result["monthly"]:
        print(f"{month['evaluation_month']}: lambda={month['selected_lambda']}, "
              f"selected EUR {month['selected']['total_profit_eur']:.2f}, "
              f"risk-neutral EUR {month['risk_neutral']['total_profit_eur']:.2f}")


if __name__ == "__main__":
    main()
