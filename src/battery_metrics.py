"""Realized daily net-P&L metrics; distinct from optimization scenario risk."""
import numpy as np


def summarize_net(profits, alpha=.95, accounting=None):
    """Equal-mass empirical loss VaR and exact (1-alpha) upper-tail CVaR.

    VaR is the inverse empirical CDF. CVaR fractionally weights the boundary
    observation, matching the Rockafellar-Uryasev discrete loss convention.
    Negative loss risk values are valid. Standard deviation uses ddof=0.
    """
    x = np.asarray(profits, dtype=float)
    if x.ndim != 1 or not x.size or not np.isfinite(x).all() or not 0 < alpha < 1:
        raise ValueError("Finite nonempty daily profits and 0 < alpha < 1 required")
    losses = np.sort(-x)
    var = float(losses[int(np.ceil(alpha * len(x))) - 1])
    cvar = float(var + np.maximum(losses - var, 0).sum() / (len(x) * (1 - alpha)))
    cumulative = np.r_[0., np.cumsum(x)]
    drawdown = np.maximum.accumulate(cumulative) - cumulative
    result = {
        "days": len(x), "total_profit_eur": float(x.sum()),
        "net_profit_eur": float(x.sum()), "mean_daily_profit_eur": float(x.mean()),
        "median_daily_profit_eur": float(np.median(x)),
        "std_daily_profit_eur": float(x.std()), "min_daily_profit_eur": float(x.min()),
        "worst_daily_net_loss_eur": float(max(0, -x.min())),
        "negative_profit_days": int((x < 0).sum()),
        "negative_profit_days_pct": float(100 * (x < 0).mean()),
        "maximum_drawdown_eur": float(drawdown.max()),
        "empirical_var_loss_eur": var, "empirical_cvar_loss_eur": cvar,
        "risk_convention": "inverse_ecdf_var_exact_fractional_tail_cvar",
        "cumulative_net_profit_eur": cumulative[1:].tolist(),
        "drawdown_eur": drawdown[1:].tolist(),
    }
    if accounting is not None:
        if len(accounting) != len(x):
            raise ValueError("One accounting record is required per daily profit")
        if not np.allclose([r["net_profit_eur"] for r in accounting], x, atol=1e-7, rtol=1e-10):
            raise ValueError("Daily accounting does not reconcile to net profit")
        for key in accounting[0]:
            result[key] = float(sum(row[key] for row in accounting))
        volume = result["discharge_throughput_mwh"]
        result["net_profit_per_mwh_discharged"] = result["net_profit_eur"] / volume if volume > 1e-9 else None
    return result
