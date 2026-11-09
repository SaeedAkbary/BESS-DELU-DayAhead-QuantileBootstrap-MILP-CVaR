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

from battery_october_benchmark import summarize
from battery_chronological_holdout import WEIGHTS


def evaluate_months(reports, *, lookback_months=None):
    """Select lambda from earlier months, never the evaluation month."""
    if lookback_months is not None and lookback_months < 1:
        raise ValueError("lookback_months must be positive")
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
        by_month[month] = report

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
    outcomes = []
    for i, month in enumerate(months[1:], start=1):
        history = months[:i]
        if lookback_months is not None:
            history = history[-lookback_months:]
        training = [row for m in history for row in by_month[m]["daily"]]
        totals = {w: sum(row[w] for row in training) for w in WEIGHTS}
        chosen = max(WEIGHTS, key=lambda w: (totals[w], -float(w)))
        selection_cutoff = date.fromisoformat(month + "-01")
        if any(date.fromisoformat(row["day"]) >= selection_cutoff for row in training):
            raise ValueError("Risk-weight selection contains evaluation-month or future prices")
        evaluation = by_month[month]["daily"]
        selected = summarize([row[chosen] for row in evaluation], alpha)
        baseline = summarize([row["0.0"] for row in evaluation], alpha)
        outcomes.append({
            "evaluation_month": month,
            "selection_months": history,
            "selection_cutoff_exclusive": selection_cutoff.isoformat(),
            "selection_observation_count": len(training),
            "selection_rule": "maximum total realized profit in prior months; ties choose lower lambda",
            "selected_lambda": float(chosen),
            "selection_profit_eur": totals,
            "days": len(evaluation),
            "selected": selected,
            "risk_neutral": baseline,
            "oracle": summarize([row["oracle"] for row in evaluation], alpha),
            "daily": [
                {"day": row["day"], "selected": row[chosen],
                 "risk_neutral": row["0.0"], "oracle": row["oracle"]}
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
            strategy: summarize([row[strategy] for row in daily], alpha)
            for strategy in ("selected", "risk_neutral", "oracle")
        },
        "limitations": [
            "Upstream monthly scenarios and their temporal validity are not verified here",
            "Daily-cyclic battery and eligible-day exclusions are inherited from input reports",
            "Risk weight maximizes prior realized profit; not an explicit risk-return criterion",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", help="Monthly risk sensitivity JSON files")
    parser.add_argument("--lookback-months", type=int)
    parser.add_argument("--output", default="output/battery_walk_forward.json")
    args = parser.parse_args()
    reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
    result = evaluate_months(reports, lookback_months=args.lookback_months)
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
