"""Day-ahead battery MILP: deterministic, risk-aware and perfect-foresight dispatch.

Prices are EUR/MWh, power MW, energy MWh. All schedules are fixed before
the realized price path is known. Inputs are illustrative until site specs
are verified. Install pyomo and highspy to solve.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Battery:
    capacity_mwh: float
    power_mw: float
    eta_charge: float
    eta_discharge: float
    initial_mwh: float
    terminal_mwh: float | None = None
    variable_cost_eur_mwh: float = 0.0

    def validate(self):
        if self.capacity_mwh <= 0 or self.power_mw <= 0:
            raise ValueError("Capacity and power must be positive")
        if not (0 < self.eta_charge <= 1 and 0 < self.eta_discharge <= 1):
            raise ValueError("Efficiencies must be in (0, 1]")
        for value in (self.initial_mwh, self.terminal_mwh):
            if value is not None and not (0 <= value <= self.capacity_mwh):
                raise ValueError("SOC energy must lie within capacity")
        if self.variable_cost_eur_mwh < 0:
            raise ValueError("Variable cost cannot be negative")


def build_model(prices, battery: Battery, *, dt_hours=0.25,
                risk_weight=0.0, alpha=0.95, probabilities=None):
    """Build a nonanticipative single-stage stochastic battery MILP.

    prices: (scenarios, time) array; deterministic inputs may be 1-D.
    risk_weight multiplies CVaR of *loss*, so it is nonnegative.
    Terminal energy defaults to initial energy to avoid end effects.
    """
    from pyomo.environ import (
        ConcreteModel, RangeSet, Var, Binary, NonNegativeReals, Reals,
        Constraint, Expression, Objective, maximize, value,
    )
    battery.validate()
    p = np.asarray(prices, dtype=float)
    if p.ndim == 1:
        p = p[None, :]
    if p.ndim != 2 or not p.size or not np.isfinite(p).all():
        raise ValueError("Prices must be a nonempty finite 1D/2D array")
    ns, nt = p.shape
    if dt_hours <= 0 or not (0 < alpha < 1) or risk_weight < 0:
        raise ValueError("Invalid dt, alpha, or risk weight")
    w = np.full(ns, 1.0 / ns) if probabilities is None else np.asarray(probabilities, dtype=float)
    if w.shape != (ns,) or np.any(w < 0) or not np.isfinite(w).all() or not np.isclose(w.sum(), 1):
        raise ValueError("Probabilities must be nonnegative and sum to one")

    m = ConcreteModel()
    m.T = RangeSet(0, nt - 1)
    m.E = RangeSet(0, nt)
    m.S = RangeSet(0, ns - 1)
    m.charge = Var(m.T, domain=NonNegativeReals, bounds=(0, battery.power_mw))
    m.discharge = Var(m.T, domain=NonNegativeReals, bounds=(0, battery.power_mw))
    m.mode = Var(m.T, domain=Binary)
    m.energy = Var(m.E, domain=NonNegativeReals, bounds=(0, battery.capacity_mwh))
    m.initial = Constraint(expr=m.energy[0] == battery.initial_mwh)
    terminal = battery.initial_mwh if battery.terminal_mwh is None else battery.terminal_mwh
    m.terminal = Constraint(expr=m.energy[nt] == terminal)
    m.charge_limit = Constraint(m.T, rule=lambda m, t: m.charge[t] <= battery.power_mw * m.mode[t])
    m.discharge_limit = Constraint(m.T, rule=lambda m, t: m.discharge[t] <= battery.power_mw * (1 - m.mode[t]))
    m.balance = Constraint(m.T, rule=lambda m, t:
        m.energy[t + 1] == m.energy[t] + dt_hours *
        (battery.eta_charge * m.charge[t] - m.discharge[t] / battery.eta_discharge))

    m.profit = Expression(m.S, rule=lambda m, s: sum(
        dt_hours * (p[s, t] * (m.discharge[t] - m.charge[t])
                    - battery.variable_cost_eur_mwh * (m.charge[t] + m.discharge[t]))
        for t in m.T))
    m.expected_profit = Expression(expr=sum(float(w[s]) * m.profit[s] for s in m.S))
    if risk_weight:
        m.var_loss = Var(domain=Reals)
        m.excess_loss = Var(m.S, domain=NonNegativeReals)
        m.tail = Constraint(m.S, rule=lambda m, s: m.excess_loss[s] >= -m.profit[s] - m.var_loss)
        m.cvar_loss = Expression(expr=m.var_loss +
            sum(float(w[s]) * m.excess_loss[s] for s in m.S) / (1 - alpha))
        m.objective = Objective(expr=m.expected_profit - risk_weight * m.cvar_loss, sense=maximize)
    else:
        m.objective = Objective(expr=m.expected_profit, sense=maximize)
    return m


def solve_dispatch(prices, battery: Battery, *, solver="appsi_highs", **kwargs):
    """Solve model and return fixed schedule and scenario profits."""
    from pyomo.environ import SolverFactory, TerminationCondition, value
    m = build_model(prices, battery, **kwargs)
    opt = SolverFactory(solver)
    if not opt.available(exception_flag=False):
        raise RuntimeError("Install a MILP solver (pip install highspy)")
    result = opt.solve(m)
    if result.solver.termination_condition != TerminationCondition.optimal:
        raise RuntimeError(f"Solver did not prove optimality: {result.solver.termination_condition}")
    return {
        "charge_mw": [value(m.charge[t]) for t in m.T],
        "discharge_mw": [value(m.discharge[t]) for t in m.T],
        "energy_mwh": [value(m.energy[t]) for t in m.E],
        "scenario_profit_eur": [value(m.profit[s]) for s in m.S],
        "expected_profit_eur": value(m.expected_profit),
        "objective_eur": value(m.objective),
    }


def deterministic(scenarios, battery, **kwargs):
    """Optimize against the scenario mean, not realized prices."""
    return solve_dispatch(np.mean(np.asarray(scenarios), axis=0), battery, **kwargs)


def stochastic(scenarios, battery, *, risk_weight=1.0, alpha=0.95, **kwargs):
    """One schedule for every scenario; CVaR is a loss-tail penalty."""
    return solve_dispatch(scenarios, battery, risk_weight=risk_weight, alpha=alpha, **kwargs)


def perfect_foresight(realized_prices, battery, **kwargs):
    """Ex-post oracle benchmark; never an executable day-ahead strategy."""
    return solve_dispatch(realized_prices, battery, **kwargs)
