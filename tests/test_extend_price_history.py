"""Tests for validated history extension without network access."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from extend_price_history import extend_history


class HistoryExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.csv"
        start = pd.Timestamp("2026-10-01", tz="Europe/Berlin")
        end = pd.Timestamp("2026-11-01", tz="Europe/Berlin")
        utc = pd.date_range(start, end, freq="15min", inclusive="left").tz_convert("UTC")
        pd.DataFrame({"timestamp_utc": utc, "price_eur_mwh": 10.0}).to_csv(
            self.path, index=False)

    def test_rejects_unfinished_month(self):
        with self.assertRaises(ValueError):
            extend_history(self.path, "2026-11", today=date(2026, 11, 7))

    def test_existing_month_needs_no_fetch(self):
        result = extend_history(
            self.path, "2026-10", today=date(2026, 11, 7),
            fetcher=lambda *args: self.fail("Unexpected network request"))
        self.assertEqual(len(result), 31 * 96 + 4)

    def test_fetches_next_month(self):
        def fake_fetch(start, end):
            self.assertEqual((start, end), ("2026-11-01", "2026-11-30"))
            utc = pd.date_range(
                pd.Timestamp("2026-11-01", tz="Europe/Berlin"),
                pd.Timestamp("2026-12-01", tz="Europe/Berlin"),
                freq="15min", inclusive="left").tz_convert("UTC")
            return pd.DataFrame({"timestamp_utc": utc, "price_eur_mwh": 20.0})
        result = extend_history(
            self.path, "2026-11", today=date(2026, 12, 1),
            fetcher=fake_fetch)
        self.assertEqual(len(result), 31 * 96 + 4 + 30 * 96)

    def test_rejects_gaps_in_existing_history(self):
        base = pd.read_csv(self.path)
        base.drop(index=100).to_csv(self.path, index=False)
        with self.assertRaisesRegex(ValueError, "missing intervals"):
            extend_history(self.path, "2026-10", today=date(2026, 11, 7))

    def test_rejects_missing_existing_price(self):
        base = pd.read_csv(self.path)
        base.loc[100, "price_eur_mwh"] = float("nan")
        base.to_csv(self.path, index=False)
        with self.assertRaisesRegex(ValueError, "Missing historical prices"):
            extend_history(self.path, "2026-10", today=date(2026, 11, 7))

    def test_rejects_truncated_existing_history(self):
        base = pd.read_csv(self.path)
        base.iloc[:-1].to_csv(self.path, index=False)
        with self.assertRaisesRegex(ValueError, "end of a local day"):
            extend_history(self.path, "2026-10", today=date(2026, 11, 7))

    def test_rejects_missing_intervals(self):
        def incomplete(start, end):
            return pd.DataFrame({
                "timestamp_utc": [pd.Timestamp("2026-11-01", tz="UTC")],
                "price_eur_mwh": [20.0],
            })
        with self.assertRaises(ValueError):
            extend_history(self.path, "2026-11", today=date(2026, 12, 1),
                           fetcher=incomplete)


if __name__ == "__main__":
    unittest.main()
