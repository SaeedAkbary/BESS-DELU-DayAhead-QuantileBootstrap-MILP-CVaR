"""Shared grid-side accounting. EUR/MWh times MW times hours yields EUR."""
import numpy as np


COST_FIELDS = ("variable_cost_eur_mwh", "purchase_fee_eur_mwh",
               "sale_fee_eur_mwh", "execution_cost_eur_mwh",
               "degradation_eur_mwh_discharged")


def interval_net_profit(price, charge, discharge, battery):
    """EUR/hour expression, usable with floats, arrays and Pyomo variables."""
    return (price * (discharge - charge)
            - battery.purchase_fee_eur_mwh * charge
            - battery.sale_fee_eur_mwh * discharge
            - battery.degradation_eur_mwh_discharged * discharge
            - (battery.variable_cost_eur_mwh + battery.execution_cost_eur_mwh)
            * (charge + discharge))


def account_dispatch(schedule, actual, battery, *, dt_hours=.25):
    """Reconcile energy cashflows and costs; discharge is grid-side MWh.

    Purchase costs and sales revenue remain signed at negative prices.
    Legacy variable cost is other variable O&M, never an alias for degradation.
    """
    battery.validate()
    charge, discharge, prices = (np.asarray(x, dtype=float) for x in
        (schedule["charge_mw"], schedule["discharge_mw"], actual))
    if (prices.ndim != 1 or not prices.size or prices.shape != charge.shape
            or charge.shape != discharge.shape):
        raise ValueError("Prices and dispatch must be equal nonempty 1D arrays")
    if not all(np.isfinite(x).all() for x in (charge, discharge, prices)):
        raise ValueError("Prices and dispatch must be finite")
    if not np.isfinite(dt_hours) or dt_hours <= 0:
        raise ValueError("Interval duration must be finite and positive")
    if np.any(charge < -1e-7) or np.any(discharge < -1e-7):
        raise ValueError("Dispatch power cannot be negative")
    q, d = float(charge.sum() * dt_hours), float(discharge.sum() * dt_hours)
    sales = float(np.dot(prices, discharge) * dt_hours)
    purchases = float(np.dot(prices, charge) * dt_hours)
    transactions = q * battery.purchase_fee_eur_mwh + d * battery.sale_fee_eur_mwh
    degradation = d * battery.degradation_eur_mwh_discharged
    execution = (q + d) * battery.execution_cost_eur_mwh
    om = (q + d) * battery.variable_cost_eur_mwh
    gross = sales - purchases
    return {"energy_sales_revenue_eur": sales, "energy_purchase_cost_eur": purchases,
            "gross_arbitrage_profit_eur": gross, "transaction_costs_eur": transactions,
            "degradation_costs_eur": degradation, "execution_costs_eur": execution,
            "variable_om_costs_eur": om, "other_variable_costs_eur": execution + om,
            "net_profit_eur": gross - transactions - degradation - execution - om,
            "charge_throughput_mwh": q, "discharge_throughput_mwh": d}
