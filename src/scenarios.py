"""Generate 50 day-ahead price scenarios using quantile regression and daily bootstrap.

Supports regular 96-interval days only; 92/100-interval days currently raise an error.
October 2026 prices are never used for model training or residual construction.
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor


# Three historical folds for calibration; September is reserved for separate evaluation.
FOLDS = [
    ("2026-02-01", "2026-04-01"),
    ("2026-04-01", "2026-06-01"),
    ("2026-06-01", "2026-09-01"),
]
FEATURES = ["sin_hour", "cos_hour", "sin_year", "cos_year",
            "weekday", "prev_mean", "prev_min", "prev_max"]


def prepare(csv_file):
    """Convert validated price CSV to features available before the day-ahead auction."""

    # Parse UTC timestamps first to handle the repeated autumn clock hour.
    df = pd.read_csv(csv_file)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df = df.sort_values("timestamp_utc").reset_index(drop=True)
    if df["timestamp_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps in the price file.")

    df["price_eur_mwh"] = pd.to_numeric(df["price_eur_mwh"], errors="coerce")
    if df["price_eur_mwh"].isna().any():
        raise ValueError("Missing or invalid prices.")

    # Derive delivery dates and local hours in Europe/Berlin.
    local = df["timestamp_utc"].dt.tz_convert("Europe/Berlin")
    df["day"] = local.dt.date
    hour = local.dt.hour + local.dt.minute / 60
    year_day = local.dt.dayofyear
    df["sin_hour"] = np.sin(2 * np.pi * hour / 24)
    df["cos_hour"] = np.cos(2 * np.pi * hour / 24)
    df["sin_year"] = np.sin(2 * np.pi * year_day / 365.25)
    df["cos_year"] = np.cos(2 * np.pi * year_day / 365.25)
    df["weekday"] = local.dt.dayofweek

    # Previous-day price summaries are known before the current auction.
    daily = df.groupby("day")["price_eur_mwh"].agg(["mean", "min", "max"])
    previous = daily.shift(1)  # Never use prices from the target day.
    for feature, column in [("prev_mean", "mean"), ("prev_min", "min"),
                            ("prev_max", "max")]:
        df[feature] = df["day"].map(previous[column])

    # Drop the first day because its previous-day features are unavailable.
    return df.dropna(subset=FEATURES).copy()


def fit_quantiles(train):
    """Fit three small sklearn quantile models at 10%, 50%, and 90%."""

    models = {}
    for quantile in (0.1, 0.5, 0.9):
        model = HistGradientBoostingRegressor(
            loss="quantile", quantile=quantile, max_iter=80,
            max_leaf_nodes=15, min_samples_leaf=80,
            learning_rate=0.08, random_state=42,
        )
        model.fit(train[FEATURES], train["price_eur_mwh"])
        models[quantile] = model
    return models


def predict(models, rows):
    """Order quantile predictions so the lower bound cannot exceed the median."""

    x = rows[FEATURES]
    middle = models[0.5].predict(x)
    lower = np.minimum(models[0.1].predict(x), middle)
    upper = np.maximum(models[0.9].predict(x), middle)
    return lower, middle, upper


def scale_residual(actual, lower, middle, upper):
    """Normalize positive and negative errors by the corresponding quantile spread."""

    # A 1 EUR/MWh floor prevents division by zero in low-volatility periods.
    error = actual - middle
    positive_spread = np.maximum(upper - middle, 1.0)
    negative_spread = np.maximum(middle - lower, 1.0)
    return np.where(error >= 0, error / positive_spread, error / negative_spread)


def score_quantile(scores, target_coverage=0.80):
    """Return a finite-sample-adjusted empirical quantile of prior scores."""

    scores = np.asarray(scores)
    if len(scores) == 0:
        raise ValueError("No prior calibration scores are available.")
    # Determine the quantile rank using only past observations.
    rank = min(len(scores) - 1, int(np.ceil((len(scores) + 1) * target_coverage)) - 1)
    return float(np.sort(scores)[rank])


def calibration_gap(actual, lower, upper, target_coverage=0.80):
    """Measure deviations outside the raw price interval using past errors."""

    scores = np.maximum.reduce([lower - actual, actual - upper,
                                np.zeros(len(actual))])
    return score_quantile(scores, target_coverage)


def coverage_rate(actual, lower, upper):
    """Calculate the fraction of observed prices within the interval."""

    return float(np.mean((actual >= lower) & (actual <= upper)))


def past_residual_days(table):
    """Construct daily residuals and calibration margins using temporal folds."""

    # Calibrate on February through August without using September.
    parts = []
    for start, end in FOLDS:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        train = table[table["day"] < first]
        valid = table[(table["day"] >= first) & (table["day"] < last)].copy()
        if len(train) < 2000 or valid.empty:
            raise ValueError("Insufficient historical data for temporal validation.")

        # Each fold trains only on months preceding that fold.
        lower, middle, upper = predict(fit_quantiles(train), valid)
        valid["lower"], valid["middle"], valid["upper"] = lower, middle, upper
        parts.append(valid)

    # Combine genuinely out-of-sample residuals.
    past = pd.concat(parts, ignore_index=True)
    actual = past["price_eur_mwh"].to_numpy()
    lower = past["lower"].to_numpy()
    middle = past["middle"].to_numpy()
    upper = past["upper"].to_numpy()
    raw_coverage = coverage_rate(actual, lower, upper)

    # Only this calibration period may determine the margin.
    gap = calibration_gap(actual, lower, upper)
    calibrated_coverage = coverage_rate(actual, lower - gap, upper + gap)

    # Construct normalized errors for full daily paths using the adjusted interval.
    # Apply the same interval-width adjustment on the target day.
    past["residual"] = scale_residual(actual, lower - gap, middle, upper + gap)
    days = []
    for _, one_day in past.groupby("day", sort=True):
        if len(one_day) == 96:
            days.append(one_day["residual"].to_numpy())

    # Daily bootstrap requires enough distinct historical days.
    if len(days) < 50:
        raise ValueError("Fewer than 50 valid historical residual days.")
    # This table supports rolling calibration and contains only past days.
    past["score"] = np.maximum.reduce([lower - actual, actual - upper,
                                       np.zeros(len(actual))])
    return np.array(days), gap, raw_coverage, calibrated_coverage, past[["day", "score"]]


def september_diagnostic(table, residuals, fixed_gap, past_scores):
    """Compare September coverage under fixed and rolling calibration.

    The rolling method was designed after inspecting fixed-method results;
    therefore September is no longer a pristine untouched test period.
    """

    first, last = date(2026, 9, 1), date(2026, 10, 1)
    train = table[table["day"] < first]
    valid = table[(table["day"] >= first) & (table["day"] < last)]
    lower, middle, upper = predict(fit_quantiles(train), valid)
    actual = valid["price_eur_mwh"].to_numpy()

    # Retain previous-method metrics for a transparent comparison.
    before = coverage_rate(actual, lower, upper)
    after = coverage_rate(actual, lower - fixed_gap, upper + fixed_gap)
    valid = valid.assign(lower=lower, middle=middle, upper=upper)

    # Historical errors are available; September days enter sequentially.
    errors = past_scores.copy()
    count_inside, total, scenarios_inside, n_days = 0, 0, 0, 0
    # Track error-to-10-90-percentile-width ratios for next-month adjustment.
    risk_ratios = []
    for day, one_day in valid.groupby("day", sort=True):
        if len(one_day) != 96:
            continue

        # At each day start, use errors from the previous 30 calendar days only.
        recent = errors[(errors["day"] < day) &
                        (errors["day"] >= day - timedelta(days=30))]
        if len(recent) < 96 * 10:
            raise ValueError("Fewer than ten historical error days in the rolling window.")
        day_gap = score_quantile(recent["score"].to_numpy())

        # Set calibrated bounds before observing this day's realized prices.
        lo = one_day["lower"].to_numpy()
        mid = one_day["middle"].to_numpy()
        hi = one_day["upper"].to_numpy()
        actual_day = one_day["price_eur_mwh"].to_numpy()
        count_inside += int(((actual_day >= lo - day_gap) &
                             (actual_day <= hi + day_gap)).sum())

        # Empirical 10th-to-90th scenario percentile coverage is a separate metric.
        paths = sample_scenarios(mid, lo - day_gap, hi + day_gap,
                                 residuals, seed=42 + n_days)
        band10, band90 = np.quantile(paths, [0.1, 0.9], axis=0)
        scenarios_inside += int(((actual_day >= band10) &
                                 (actual_day <= band90)).sum())
        # Determine positive and negative scenario expansion around the median.
        positive_width = np.maximum(band90 - mid, 1.0)
        negative_width = np.maximum(mid - band10, 1.0)
        ratios_day = np.where(actual_day >= mid,
                              (actual_day - mid) / positive_width,
                              (mid - actual_day) / negative_width)
        risk_ratios.extend(ratios_day)
        total += len(one_day)
        n_days += 1

        # Once the day ends, its realized price may enter the next day's history.
        scores = np.maximum.reduce([lo - actual_day, actual_day - hi,
                                    np.zeros(len(actual_day))])
        errors = pd.concat([
            errors, pd.DataFrame({"day": [day] * len(scores), "score": scores})
        ], ignore_index=True)

    if total == 0:
        raise ValueError("No regular September days available for evaluation.")

    # September errors are known by month-end and can inform October forecasts.
    sep = errors[(errors["day"] >= first) & (errors["day"] < last)]
    gap_october = score_quantile(sep["score"].to_numpy())
    # Set one October scenario-width factor only after September ends.
    scenario_factor = max(1.0, score_quantile(np.array(risk_ratios)))
    return (before, after, count_inside / total, scenarios_inside / total,
            n_days, gap_october, scenario_factor)


def sample_scenarios(median, lower, upper, historical_days, seed=42, count=50):
    """Sample 50 complete daily paths from historical daily residuals."""

    if historical_days.shape[1] != len(median):
        raise ValueError("Historical and target daily path lengths differ.")

    # Sample one index for an entire day, not separately for each hour.
    rng = np.random.default_rng(seed)
    selected = historical_days[rng.choice(len(historical_days), count, replace=True)]
    upper_spread = np.maximum(upper - median, 1.0)
    lower_spread = np.maximum(median - lower, 1.0)

    # Rescale normalized residuals to the new day's uncertainty.
    spreads = np.where(selected >= 0, upper_spread, lower_spread)
    return median + selected * spreads


def evaluate_october(table, models, residuals, gap, factor):
    """October final evaluation: read actual prices only after scenarios exist."""

    october = table[(table["day"] >= date(2026, 10, 1)) &
                    (table["day"] <= date(2026, 10, 31))]
    in_band, in_scenarios, n, n_days = 0, 0, 0, 0
    for day, rows in october.groupby("day", sort=True):
        # The current implementation excludes the 100-interval autumn DST day.
        if len(rows) != 96:
            continue
        low, median, high = predict(models, rows)
        low, high = low - gap, high + gap
        # Target-day prices were not used to construct scenarios.
        paths = sample_scenarios(median, low, high, residuals,
                                 seed=42 + n_days)
        paths = median + factor * (paths - median)
        p10, p90 = np.quantile(paths, [0.1, 0.9], axis=0)
        actual = rows["price_eur_mwh"].to_numpy()
        in_band += int(((actual >= low) & (actual <= high)).sum())
        in_scenarios += int(((actual >= p10) & (actual <= p90)).sum())
        n += len(actual)
        n_days += 1
    if n == 0:
        raise ValueError("No regular October days available for evaluation.")
    return in_band / n, in_scenarios / n, n_days


def main():
    """Read history and save scenarios for one October 2026 day."""

    parser = argparse.ArgumentParser(description="50 DE-LU price scenarios using sklearn")
    parser.add_argument("--input", required=True, help="Validated historical CSV")
    parser.add_argument("--date", default="2026-10-15", help="Evaluation day YYYY-MM-DD")
    parser.add_argument("--output", default="output/scenarios_2026-10-15.csv")
    args = parser.parse_args()
    target = date.fromisoformat(args.date)

    # Exclude all October data from training; evaluate one regular day.
    if not (date(2026, 10, 1) <= target <= date(2026, 10, 31)):
        raise ValueError("The evaluation date must be in October 2026.")

    table = prepare(args.input)
    cutoff = date(2026, 10, 1)
    train = table[table["day"] < cutoff]
    test = table[table["day"] == target]
    if len(test) != 96:
        raise ValueError("Only regular 96-interval days are supported.")

    # Initial calibration uses February through August; September is development data.
    residuals, gap, raw_calib, fixed_calib, past_scores = past_residual_days(train)
    raw_sep, fixed_sep, rolling_sep, scenario_sep, sep_days, october_gap, factor = (
        september_diagnostic(train, residuals, gap, past_scores)
    )

    # Final models train through September; October prices never enter training.
    models = fit_quantiles(train)
    # Report October metrics only after calibration settings are fixed.
    october_band, october_paths, october_days = evaluate_october(
        table, models, residuals, october_gap, factor
    )
    lower, middle, upper = predict(models, test)
    # Final calibration margin is based on September 2026 errors only.
    lower, upper = lower - october_gap, upper + october_gap
    scenarios = sample_scenarios(middle, lower, upper, residuals)
    # The September-derived factor widens paths around the central forecast.
    scenarios = middle + factor * (scenarios - middle)
    p10, p90 = np.quantile(scenarios, [0.1, 0.9], axis=0)

    # Output contains forecasts and scenarios, not actual target-day prices.
    # A calibrated interval is not necessarily a true q10/q90 quantile interval.
    result = pd.DataFrame({
        "timestamp_utc": test["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lower_calibrated": lower, "q50_forecast": middle, "upper_calibrated": upper,
        "scenario_p10": p10, "scenario_p90": p90,
    })
    for i, one_path in enumerate(scenarios, start=1):
        result[f"scenario_{i:02d}"] = one_path

    # Output contains 50 scenario columns and three quantile columns.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Evaluation day: {target}; intervals: {len(test)}")
    print(f"Out-of-sample residual days: {len(residuals)}")
    print(f"February-August calibration margin: {gap:.2f} EUR/MWh")
    print(f"Calibration coverage before/after adjustment: {raw_calib:.3f} / {fixed_calib:.3f}")
    print(f"September ({sep_days} days), raw/fixed/rolling coverage: "
          f"{raw_sep:.3f} / {fixed_sep:.3f} / {rolling_sep:.3f}")
    print(f"September rolling scenario 10th-90th percentile coverage: {scenario_sep:.3f}")
    print(f"Past-only margin for October start: {october_gap:.2f} EUR/MWh")
    print(f"Scenario width factor (September only): {factor:.3f}")
    print(f"October evaluation ({october_days} regular days), "
          f"interval/scenario percentile coverage: {october_band:.3f} / {october_paths:.3f}")
    print("Warning: September is a development month; October 25 DST day is excluded.")
    print(f"Generated 50 equally weighted scenarios (1/50 each): {args.output}")
    print("Note: marginal calibration does not validate CVaR or economic performance.")


if __name__ == "__main__":
    main()
