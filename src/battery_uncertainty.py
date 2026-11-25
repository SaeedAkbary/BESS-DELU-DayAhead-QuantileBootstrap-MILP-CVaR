"""Paired day-level bootstrap uncertainty for walk-forward battery profits.

Bootstrap resamples delivery days as paired observations so both strategies
are evaluated on the same sampled days. Confidence intervals are descriptive
and do not establish independent market-month generalization.
"""
import numpy as np


def paired_profit_bootstrap(daily, *, n_boot=5000, seed=42, confidence=.95):
    """Estimate uncertainty in selected minus risk-neutral total profit.

    The interval applies to the mean daily profit difference. Daily
    observations may be serially dependent; use month-block inference once
    enough evaluation months are available.
    """
    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between 0 and 1")
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    if not daily:
        raise ValueError("At least one evaluation day is required")
    differences = np.asarray(
        [row["selected"] - row["risk_neutral"] for row in daily], dtype=float)
    if not np.isfinite(differences).all():
        raise ValueError("Daily profit differences must be finite")
    rng = np.random.default_rng(seed)
    bootstrap_means = np.empty(n_boot)
    for i in range(n_boot):
        bootstrap_means[i] = rng.choice(differences, len(differences),
                                        replace=True).mean()
    lower, upper = np.quantile(
        bootstrap_means, [(1 - confidence) / 2, (1 + confidence) / 2])
    return {
        "method": "paired_iid_day_bootstrap",
        "confidence": confidence,
        "bootstrap_samples": n_boot,
        "seed": seed,
        "days": len(differences),
        "mean_daily_difference_eur": float(differences.mean()),
        "total_difference_eur": float(differences.sum()),
        "mean_daily_difference_ci_eur": [float(lower), float(upper)],
        "probability_positive_mean_bootstrap": float(
            np.mean(bootstrap_means > 0)),
        "limitations": [
            "Day-level iid resampling ignores serial dependence and month effects",
            "Bootstrap probability is not a frequentist p-value",
            "Small numbers of evaluation months cannot establish generalization",
        ],
    }


def month_block_profit_bootstrap(daily, *, n_boot=5000, seed=42,
                                 confidence=.95, min_months=3):
    """Resample complete evaluation months to retain within-month dependence.

    Returns an explicitly unavailable interval when too few months exist.
    This is descriptive inference, not proof of future generalization.
    """
    from collections import defaultdict
    from datetime import date

    if not 0 < confidence < 1:
        raise ValueError("confidence must be strictly between 0 and 1")
    if n_boot < 1 or min_months < 2:
        raise ValueError("n_boot must be positive and min_months >= 2")
    groups = defaultdict(list)
    for row in daily:
        day = date.fromisoformat(row["day"])
        difference = float(row["selected"]) - float(row["risk_neutral"])
        if not np.isfinite(difference):
            raise ValueError("Daily profit differences must be finite")
        groups[day.strftime("%Y-%m")].append(difference)
    if len(groups) < min_months:
        return {
            "method": "paired_month_block_bootstrap",
            "status": "insufficient_months",
            "observed_months": len(groups),
            "required_months": min_months,
            "mean_daily_difference_ci_eur": None,
            "limitations": ["Month-block inference withheld until enough evaluation months exist"],
        }
    blocks = [np.asarray(values) for _, values in sorted(groups.items())]
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        indices = rng.integers(0, len(blocks), size=len(blocks))
        selected = [blocks[j] for j in indices]
        means[i] = sum(block.sum() for block in selected) / sum(len(block) for block in selected)
    lower, upper = np.quantile(means, [(1 - confidence) / 2, (1 + confidence) / 2])
    return {
        "method": "paired_month_block_bootstrap",
        "status": "available",
        "observed_months": len(blocks),
        "required_months": min_months,
        "confidence": confidence,
        "bootstrap_samples": n_boot,
        "seed": seed,
        "mean_daily_difference_ci_eur": [float(lower), float(upper)],
        "limitations": ["Few monthly blocks can yield unstable confidence intervals"],
    }
