"""Fetch real DE-LU day-ahead electricity prices from Energy-Charts."""

# Import CLI argument parsing.
import argparse
# Calculate the following calendar day.
from datetime import timedelta
# Create the output directory if necessary.
from pathlib import Path

# Use pandas for tabular and timezone-aware data.
import pandas as pd
# Use requests for API calls.
import requests


# Official API endpoint and bidding zone.
API_URL = "https://api.energy-charts.info/price"
ZONE = "DE-LU"
TIMEZONE = "Europe/Berlin"


def validate_prices(df, start, end):
    """Validate complete 15-minute price intervals, including DST transition days."""

    # Sort records by UTC timestamp.
    df = df.sort_values("timestamp_utc").reset_index(drop=True)

    # Reject missing timestamps or invalid prices.
    if df[["timestamp_utc", "price_eur_mwh"]].isna().any().any():
        raise ValueError("API response contains an invalid or missing price or timestamp.")

    # Reject duplicate timestamps.
    if df["timestamp_utc"].duplicated().any():
        raise ValueError("Duplicate timestamps in price data.")

    # Validate each Berlin calendar day.
    for day in pd.date_range(start, end, freq="D"):
        # Local midnight accounts for DST transitions.
        first = pd.Timestamp(day.date(), tz=TIMEZONE)
        # Use the next local midnight, not a fixed 24-hour offset.
        following = pd.Timestamp(day.date() + timedelta(days=1), tz=TIMEZONE)

        # Generate 92, 96 or 100 expected quarter-hour timestamps.
        expected = pd.date_range(first, following, freq="15min", inclusive="left")
        # Select records for the current day.
        observed = df.loc[
            (df["timestamp_utc"] >= first.tz_convert("UTC"))
            & (df["timestamp_utc"] < following.tz_convert("UTC")),
            "timestamp_utc",
        ]
        # Reject missing or extra intervals.
        # Compare timestamps in UTC to distinguish repeated autumn hours.
        expected_utc = expected.tz_convert("UTC")
        if len(observed) != len(expected_utc) or set(observed) != set(expected_utc):
            raise ValueError(
                f"Day {day.date()} is incomplete: {len(observed)} "
                f"intervals instead of {len(expected)} expected 15-minute intervals."
            )

    # Return validated data.
    return df


def fetch_prices(start, end):
    """Fetch actual API prices and validate them."""

    # Require ordered start and end dates.
    if pd.Timestamp(start) > pd.Timestamp(end):
        raise ValueError("Start date must not be later than end date.")

    # Both dates are inclusive in the API.
    parameters = {"bzn": ZONE, "start": start, "end": end}
    # Send a request with a 60-second timeout.
    response = requests.get(API_URL, params=parameters, timeout=60)
    # Propagate server errors including HTTP 429.
    response.raise_for_status()
    # Parse the JSON response.
    raw = response.json()

    # Normalize whitespace in the EUR/MWh unit.
    if str(raw.get("unit", "")).replace(" ", "") != "EUR/MWh":
        raise ValueError(f"Unexpected price unit: {raw.get('unit')}")

    # Require matching timestamp and price arrays.
    times, prices = raw.get("unix_seconds"), raw.get("price")
    if not isinstance(times, list) or not isinstance(prices, list) or len(times) != len(prices):
        raise ValueError("API response has invalid timestamp or price arrays.")

    # Build a two-column table.
    df = pd.DataFrame({"unix_seconds": times, "price_eur_mwh": prices})
    # Convert invalid prices to NaN for validation.
    df["price_eur_mwh"] = pd.to_numeric(df["price_eur_mwh"], errors="coerce")
    # Convert Unix seconds to UTC.
    df["timestamp_utc"] = pd.to_datetime(df["unix_seconds"], unit="s", utc=True)
    # Add Berlin timestamps for delivery-day validation.
    df["timestamp_berlin"] = df["timestamp_utc"].dt.tz_convert(TIMEZONE)

    # Return data only after validation.
    return validate_prices(df, start, end)


def main():
    """Read CLI dates, download prices and write reproducible CSV."""

    # Define configurable CLI parameters.
    parser = argparse.ArgumentParser(description="Download DE-LU 15-minute day-ahead prices")
    parser.add_argument("--start", default="2026-10-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2026-10-31", help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="prices_DE-LU.csv", help="CSV output filename")
    # Parse user arguments.
    args = parser.parse_args()

    # Validate before writing files.
    df = fetch_prices(args.start, args.end)
    # Create the destination directory after validation.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    # Preserve negative prices and UTC/Berlin timestamps.
    df[["timestamp_utc", "timestamp_berlin", "price_eur_mwh"]].to_csv(
        args.output, index=False
    )
    # Report the number of validated intervals.
    print(f"{len(df)} validated intervals saved: {args.output}")
    # Display the source for attribution.
    print("Source: Energy-Charts.info / Bundesnetzagentur (CC BY 4.0)")


# Execute only when invoked directly.
if __name__ == "__main__":
    main()
