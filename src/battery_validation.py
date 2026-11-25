"""Calendar completeness gates for historical research, not vintage validation."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from data import validate_prices


def completed_month(month, today=None):
    first = date.fromisoformat(month + "-01")
    end = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    today = today or datetime.now(ZoneInfo("Europe/Lisbon")).date()
    if end > today:
        raise ValueError(f"Evaluation month {month} is not complete as of {today}")
    return first, end


def validate_month_table(table, month, today=None):
    first, end = completed_month(month, today)
    validate_prices(table, first, end - timedelta(days=1))


def validate_report_calendar(report, today=None):
    first, end = completed_month(report["month"], today)
    expected = {d.date().isoformat() for d in pd.date_range(first, end, inclusive="left")}
    evaluated = {r["day"] for r in report["daily"]}
    skipped = report.get("skipped_days", [])
    exclusions = [r["day"] for r in skipped]
    if len(set(exclusions)) != len(exclusions) or evaluated.intersection(exclusions):
        raise ValueError("Duplicate or overlapping excluded days")
    if evaluated.union(exclusions) != expected:
        raise ValueError("Monthly report must account for every calendar day")
    if any(not r.get("reason") for r in skipped):
        raise ValueError("Skipped days require an explicit reason")
