"""Chronological risk-weight selection and holdout evaluation.

Select lambda using October 1-15 only, then evaluate October 16-31.
The price scenario model is trained before October. No holdout realized
profits are used to select lambda. This is a single-month split, not a
multi-month robustness study.
"""
import argparse
import json
from pathlib import Path

from battery_october_benchmark import summarize

WEIGHTS = ("0.0", "0.25", "0.5", "1.0", "2.0")
SPLIT_DAY = "2026-10-16"


def evaluate(report):
    """Choose the highest calibration profit; break ties toward lower risk."""
    daily = report["daily"]
    calibration = [r for r in daily if r["day"] < SPLIT_DAY]
    holdout = [r for r in daily if r["day"] >= SPLIT_DAY]
    if not calibration or not holdout:
        raise ValueError("Both chronological partitions need eligible days")

    # Do not inspect holdout profits until lambda is fixed.
    calibration_totals = {
        w: sum(row[w] for row in calibration) for w in WEIGHTS
    }
    selected = max(WEIGHTS, key=lambda w: (calibration_totals[w], -float(w)))
    alpha = report["alpha"]
    baseline = "0.0"

    def stats(rows, weight):
        return summarize([r[weight] for r in rows], alpha)

    selected_holdout = stats(holdout, selected)
    baseline_holdout = stats(holdout, baseline)
    return {
        "split": {"calibration_before": SPLIT_DAY, "holdout_from": SPLIT_DAY},
        "selected_lambda": float(selected),
        "selection_rule": "maximum realized calibration profit; ties favor smaller lambda",
        "calibration_days": len(calibration),
        "holdout_days": len(holdout),
        "calibration_total_profit_eur": calibration_totals,
        "calibration_selected": stats(calibration, selected),
        "holdout_selected": selected_holdout,
        "holdout_risk_neutral": baseline_holdout,
        "holdout_oracle": stats(holdout, "oracle"),
        "holdout_profit_difference_eur":
            selected_holdout["total_profit_eur"] - baseline_holdout["total_profit_eur"],
        "limitations": [
            "One October holdout, not multi-month external validation",
            "October 25 DST day is excluded",
            "Battery specifications are illustrative",
            "Scenario tail calibration is provisional",
            "Risk-weight selection maximizes profit, not a combined risk metric",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="output/battery_chronological_holdout.json")
    args = p.parse_args()
    report = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = evaluate(report)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Calibration days: {result['calibration_days']}; "
          f"holdout days: {result['holdout_days']}")
    print(f"Selected lambda: {result['selected_lambda']}")
    for label in ("holdout_selected", "holdout_risk_neutral", "holdout_oracle"):
        s = result[label]
        print(f"{label}: total EUR {s['total_profit_eur']:.2f}; "
              f"empirical CVaR loss EUR {s['empirical_cvar_loss_eur']:.2f}")
    print(f"Holdout profit difference EUR {result['holdout_profit_difference_eur']:.2f}")


if __name__ == "__main__":
    main()
