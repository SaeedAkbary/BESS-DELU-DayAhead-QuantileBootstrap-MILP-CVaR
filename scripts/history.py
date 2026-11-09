"""Download and validate real 15-minute historical prices month by month."""

# Use pandas for monthly dates and table concatenation.
import pandas as pd
# Pause between API requests.
import time
# Handle API rate limits.
import requests
# Create output directories.
from pathlib import Path

# Reuse the validated downloader from data.py.
from data import fetch_prices


def main():
    """Download training and evaluation months and combine validated CSVs."""

    # Use prices from after the 15-minute market launch.
    months = pd.date_range("2025-10-01", "2026-10-01", freq="MS")

    # Append each month only after validation.
    monthly_tables = []

    # Persist each month immediately to preserve progress.
    output_dir = Path("output/history")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Request one month at a time to detect incomplete periods.
    for month in months:
        # Compute the first and last day of the month.
        start = month.strftime("%Y-%m-%d")
        end = (month + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")

        # Retry after HTTP 429 rate limits.
        for attempt in range(3):
            try:
                # Validate every interval and DST transition.
                df = fetch_prices(start, end)
                break
            except requests.HTTPError as error:
                # Propagate other server errors.
                if error.response is None or error.response.status_code != 429 or attempt == 2:
                    raise
                # Wait 60 and 120 seconds after rate limiting.
                wait = 60 * (attempt + 1)
                print(f"API rate limit (429); retrying after {wait} seconds...", flush=True)
                time.sleep(wait)

        # Persist each validated month separately.
        table = df[["timestamp_utc", "timestamp_berlin", "price_eur_mwh"]]
        table.to_csv(output_dir / f"DE-LU_{month.strftime('%Y-%m')}.csv", index=False)
        monthly_tables.append(table)
        print(f"Month {month.strftime('%Y-%m')}: {len(df)} validated intervals", flush=True)

        # Wait 15 seconds between requests.
        time.sleep(15)

    # Concatenate all monthly tables.
    result = pd.concat(monthly_tables, ignore_index=True)

    # Reject duplicate timestamps across months.
    if result["timestamp_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps across monthly files.")

    # Sort timestamps for model training.
    result = result.sort_values("timestamp_utc").reset_index(drop=True)

    # Write combined CSV only after validation.
    filename = "output/prices_DE-LU_2025-10_to_2026-10.csv"
    result.to_csv(filename, index=False)
    print(f"Total validated intervals: {len(result)}")
    print(f"Combined file: {filename}")
    print("Source: Energy-Charts.info")


# Run only when invoked directly.
if __name__ == "__main__":
    main()
