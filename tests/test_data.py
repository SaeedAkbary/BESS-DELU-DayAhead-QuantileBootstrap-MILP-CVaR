"""Unit tests for price data validation using synthetic fixtures only."""

# Python standard-library unit testing.
import unittest
# Calculate next local midnight.
from datetime import timedelta
# Create synthetic test data rows.
import pandas as pd

# Import the function under test.
from data import validate_prices


def make_day(day):
    """Generate one local day of timestamps with synthetic prices."""

    # Start at Berlin local midnight.
    start = pd.Timestamp(day, tz="Europe/Berlin")
    # Use the next local midnight to handle DST.
    next_day = pd.Timestamp(start.date() + timedelta(days=1), tz="Europe/Berlin")
    # Generate exact quarter-hour timestamps in UTC.
    times = pd.date_range(start, next_day, freq="15min", inclusive="left").tz_convert("UTC")
    # Use constant synthetic prices for software tests only.
    return pd.DataFrame({"timestamp_utc": times, "price_eur_mwh": [25.0] * len(times)})


class PriceValidationTests(unittest.TestCase):
    """Ensure incomplete or invalid data is rejected."""

    def test_normal_day(self):
        """Regular day has exactly 96 intervals."""
        df = make_day("2026-10-26")
        self.assertEqual(len(validate_prices(df, "2026-10-26", "2026-10-26")), 96)

    def test_dst_fall(self):
        """Autumn DST day has 100 intervals."""
        df = make_day("2026-10-25")
        self.assertEqual(len(validate_prices(df, "2026-10-25", "2026-10-25")), 100)

    def test_dst_spring(self):
        """Spring DST day has 92 intervals."""
        df = make_day("2026-03-29")
        self.assertEqual(len(validate_prices(df, "2026-03-29", "2026-03-29")), 92)

    def test_missing_interval_rejected(self):
        """Reject missing intervals."""
        df = make_day("2026-10-26").iloc[:-1]
        with self.assertRaises(ValueError):
            validate_prices(df, "2026-10-26", "2026-10-26")

    def test_duplicate_interval_rejected(self):
        """Reject duplicate timestamps even when row count matches."""
        df = make_day("2026-10-26")
        df.loc[1, "timestamp_utc"] = df.loc[0, "timestamp_utc"]
        with self.assertRaises(ValueError):
            validate_prices(df, "2026-10-26", "2026-10-26")

    def test_negative_price_allowed(self):
        """Allow negative market prices."""
        df = make_day("2026-10-26")
        df.loc[0, "price_eur_mwh"] = -30.0
        self.assertEqual(validate_prices(df, "2026-10-26", "2026-10-26").loc[0, "price_eur_mwh"], -30.0)


# Run tests when executed directly.
if __name__ == "__main__":
    unittest.main()
