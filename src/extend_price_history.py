"""Extend a validated historical price CSV with complete delivery months.

Never evaluate a partially elapsed calendar month. The extension fetches and
validates every local delivery interval through data.fetch_prices, preserves
the original history, and rejects overlapping or missing UTC intervals.
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from data import fetch_prices
from battery_monthly_scenarios import month_bounds


def extend_history(existing_csv, last_month, *, today=None, fetcher=fetch_prices):
    """Return validated combined history through the requested complete month."""
    start, end = month_bounds(last_month)
    today = date.today() if today is None else today
    if end > today:
        raise ValueError(f"{last_month} is not a completed month as of {today}")
    base = pd.read_csv(existing_csv)
    required = {"timestamp_utc", "price_eur_mwh"}
    if not required.issubset(base.columns):
        raise ValueError("Historical CSV lacks required columns")
    base["timestamp_utc"] = pd.to_datetime(base["timestamp_utc"], utc=True)
    if base["timestamp_utc"].isna().any() or base["timestamp_utc"].duplicated().any():
        raise ValueError("Invalid or duplicate historical timestamps")
    base = base.sort_values("timestamp_utc").reset_index(drop=True)
    if base["price_eur_mwh"].isna().any():
        raise ValueError("Missing historical prices")
    if not base["timestamp_utc"].diff().dropna().eq(pd.Timedelta(minutes=15)).all():
        raise ValueError("Existing historical prices have missing intervals")
    if base.empty:
        raise ValueError("Historical CSV is empty")
    local_last = base["timestamp_utc"].iloc[-1].tz_convert("Europe/Berlin").date()
    local_first = base["timestamp_utc"].iloc[0].tz_convert("Europe/Berlin")
    if local_first.hour != 0 or local_first.minute != 0 or local_first.day != 1:
        raise ValueError("Historical CSV must begin at the start of a local month")
    local_last_time = base["timestamp_utc"].iloc[-1].tz_convert("Europe/Berlin")
    if local_last_time.hour != 23 or local_last_time.minute != 45:
        raise ValueError("Historical CSV must end at the end of a local day")
    next_day = local_last + timedelta(days=1)
    if next_day.day != 1:
        raise ValueError("Historical CSV does not end on a full local calendar month")
    first_new = next_day
    if first_new > end:
        raise ValueError("Requested last month precedes existing history")
    parts = [base]
    cursor = first_new
    while cursor < end:
        next_month = month_bounds(cursor.strftime("%Y-%m"))[1]
        month_end = next_month - timedelta(days=1)
        new = fetcher(cursor.isoformat(), month_end.isoformat()).copy()
        new["timestamp_utc"] = pd.to_datetime(new["timestamp_utc"], utc=True)
        parts.append(new)
        cursor = next_month
    combined = pd.concat(parts, ignore_index=True)
    combined = combined.sort_values("timestamp_utc").reset_index(drop=True)
    if combined["timestamp_utc"].duplicated().any():
        raise ValueError("Overlapping historical timestamps")
    if combined["price_eur_mwh"].isna().any():
        raise ValueError("Missing historical prices")
    # Berlin delivery months are continuous in UTC, including DST changes.
    utc = combined["timestamp_utc"]
    if not utc.diff().dropna().eq(pd.Timedelta(minutes=15)).all():
        raise ValueError("Missing or irregular historical 15-minute intervals")
    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True)
    parser.add_argument("--through-month", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = extend_history(args.history, args.through_month)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(path, index=False)
    print(f"Validated {len(result)} 15-minute intervals through {args.through_month}")


if __name__ == "__main__":
    main()
