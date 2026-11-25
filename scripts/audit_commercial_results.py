"""Independently verify saved dispatch physics and cashflows against source prices."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd


def audit_results(bundle, history):
    source = Path(history)
    if hashlib.sha256(source.read_bytes()).hexdigest() != bundle["provenance"]["history_sha256"]:
        raise ValueError("Source history hash differs from the executed report")
    frame = pd.read_csv(source)
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame = frame.sort_values("timestamp_utc")
    frame["day"] = frame["timestamp_utc"].dt.tz_convert("Europe/Berlin").dt.strftime("%Y-%m-%d")
    prices = {day: rows["price_eur_mwh"].to_numpy(dtype=float) for day, rows in frame.groupby("day")}
    checks, max_cash_error, max_balance_error = 0, 0., 0.
    for case in bundle["experiments"]:
        battery = case["config"]["battery"]
        for month in case["monthly"]:
            for row in month["daily"]:
                actual = prices[row["day"]]
                for name, schedule in row["dispatch"].items():
                    c, d, e = (np.asarray(schedule[key], dtype=float) for key in ("charge_mw", "discharge_mw", "energy_mwh"))
                    if len(c) != len(actual) or len(d) != len(c) or len(e) != len(c) + 1:
                        raise ValueError("Saved schedule dimensions do not match source prices")
                    if not all(np.isfinite(v).all() for v in (c, d, e)):
                        raise ValueError("Nonfinite saved schedule")
                    tolerance = 1e-6
                    if (np.min(c) < -tolerance or np.min(d) < -tolerance or
                        np.max(c) > battery["power_mw"] + tolerance or
                        np.max(d) > battery["power_mw"] + tolerance or
                        np.min(e) < -tolerance or np.max(e) > battery["capacity_mwh"] + tolerance or
                        np.max(np.minimum(c, d)) > tolerance):
                        raise ValueError("Saved dispatch violates physical bounds or operating mode")
                    terminal = battery["initial_mwh"] if battery["terminal_mwh"] is None else battery["terminal_mwh"]
                    np.testing.assert_allclose([e[0], e[-1]], [battery["initial_mwh"], terminal], atol=tolerance, rtol=0)
                    balance = e[1:] - e[:-1] - .25 * (battery["eta_charge"] * c - d / battery["eta_discharge"])
                    max_balance_error = max(max_balance_error, float(np.max(np.abs(balance))))
                    np.testing.assert_allclose(balance, 0., atol=tolerance, rtol=0)
                    # Independent scalar arithmetic, deliberately not account_dispatch.
                    q, discharge = sum(c) / 4, sum(d) / 4
                    sales, purchases = sum(actual * d) / 4, sum(actual * c) / 4
                    fees = q * battery["purchase_fee_eur_mwh"] + discharge * battery["sale_fee_eur_mwh"]
                    wear = discharge * battery["degradation_eur_mwh_discharged"]
                    other = (q + discharge) * (battery["execution_cost_eur_mwh"] + battery["variable_cost_eur_mwh"])
                    net = sales - purchases - fees - wear - other
                    expected = dict(energy_sales_revenue_eur=sales, energy_purchase_cost_eur=purchases,
                        gross_arbitrage_profit_eur=sales-purchases, transaction_costs_eur=fees,
                        degradation_costs_eur=wear, other_variable_costs_eur=other,
                        charge_throughput_mwh=q, discharge_throughput_mwh=discharge, net_profit_eur=net)
                    for field, value in expected.items():
                        np.testing.assert_allclose(row["accounting"][name][field], value, atol=1e-6, rtol=1e-10)
                    max_cash_error = max(max_cash_error, abs(float(net) - row[name]))
                    np.testing.assert_allclose(row[name], net, atol=1e-6, rtol=1e-10)
                    if row[name] > row["oracle"] + 1e-4:
                        raise ValueError("A strategy exceeds the matching perfect-foresight bound")
                    checks += 1
            for strategy, summary in month["commercial_summary"].items():
                np.testing.assert_allclose(summary["net_profit_eur"], sum(row[strategy] for row in month["daily"]), atol=1e-6, rtol=0)
    return {"status": "passed", "schedules_checked": checks,
            "max_cash_reconciliation_error_eur": max_cash_error,
            "max_energy_balance_error_mwh": max_balance_error,
            "source_sha256": bundle["provenance"]["history_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    parser.add_argument("--history", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    report = audit_results(json.loads(Path(args.results).read_text()), args.history)
    text = json.dumps(report, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
