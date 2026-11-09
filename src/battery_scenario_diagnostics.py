"""Out-of-sample diagnostics for generated day-ahead price scenarios.

Coverage refers to the empirical 10th-90th percentile scenario band,
not to a calibrated probabilistic guarantee. Daily values are computed
only after scenarios have been fixed.
"""
import numpy as np


def scenario_diagnostics(daily_inputs):
    """Score scenario quantiles against realized 15-minute prices."""
    if not daily_inputs:
        raise ValueError("At least one eligible day is required")
    days = []
    for day, paths, actual in daily_inputs:
        paths = np.asarray(paths, dtype=float)
        actual = np.asarray(actual, dtype=float)
        if paths.ndim != 2 or actual.ndim != 1 or paths.shape[1] != len(actual):
            raise ValueError(f"Scenario/actual dimensions differ on {day}")
        if paths.shape[0] < 2 or not np.isfinite(paths).all() or not np.isfinite(actual).all():
            raise ValueError(f"Invalid scenarios or prices on {day}")
        lower, middle, upper = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
        inside = (actual >= lower) & (actual <= upper)
        days.append({
            "day": day,
            "intervals": len(actual),
            "band_10_90_coverage": float(inside.mean()),
            "mean_absolute_median_error_eur_mwh": float(np.abs(actual - middle).mean()),
            "mean_signed_median_error_eur_mwh": float((actual - middle).mean()),
            "mean_band_width_eur_mwh": float((upper - lower).mean()),
            "above_90_fraction": float((actual > upper).mean()),
            "below_10_fraction": float((actual < lower).mean()),
        })
    intervals = sum(row["intervals"] for row in days)
    return {
        "target_band_coverage": 0.8,
        "observed_band_coverage": sum(
            row["band_10_90_coverage"] * row["intervals"] for row in days) / intervals,
        "mean_absolute_median_error_eur_mwh": sum(
            row["mean_absolute_median_error_eur_mwh"] * row["intervals"]
            for row in days) / intervals,
        "mean_signed_median_error_eur_mwh": sum(
            row["mean_signed_median_error_eur_mwh"] * row["intervals"]
            for row in days) / intervals,
        "mean_band_width_eur_mwh": sum(
            row["mean_band_width_eur_mwh"] * row["intervals"]
            for row in days) / intervals,
        "above_90_fraction": sum(
            row["above_90_fraction"] * row["intervals"] for row in days) / intervals,
        "below_10_fraction": sum(
            row["below_10_fraction"] * row["intervals"] for row in days) / intervals,
        "days": days,
        "limitations": [
            "Empirical scenario quantiles from 50 paths are noisy",
            "Interval-level coverage does not measure temporal dependence or tail CVaR calibration",
            "Evaluation prices are used for scoring only, not scenario construction",
        ],
    }
