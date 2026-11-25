# Commercial backtesting methodology

## Scope

This extends the existing Pyomo/HiGHS, daily-cyclic battery framework.
It measures simulated **operating net arbitrage P&L**, not investment returns
or live trading revenue. Battery assumptions and example fees are illustrative.
No exchange tariff, grid charge or asset degradation price has been verified.
Original October documents/figures remain unchanged as research evidence.
October 2026 is development data, never an untouched holdout. November 2026
is incomplete as of 23 November 2026 and cannot be a completed result.

## Common cost identity and migration

At each interval, let q = charge_MW * dt_hours and d = discharge_MW * dt_hours,
both measured on the grid side in MWh. With price p in EUR/MWh:

```
sales          = sum(p * d)
purchases      = sum(p * q)
gross          = sales - purchases
transactions   = purchase_fee_eur_mwh * sum(q) + sale_fee_eur_mwh * sum(d)
degradation    = degradation_eur_mwh_discharged * sum(d)
execution      = execution_cost_eur_mwh * sum(q + d)
legacy O&M     = variable_cost_eur_mwh * sum(q + d)
net            = gross - transactions - degradation - execution - legacy O&M
```

Negative prices retain their signs, including negative purchase costs.
The degradation rate applies only to discharged grid-side energy, not internal
stored energy, charging throughput, or equivalent full cycles. It approximates
wear linearly; cycle depth, calendar aging and nonlinear state of health remain
future work. No second degradation convention is applied.

All cost fields default to zero. Existing positional Battery arguments retain
their order. The legacy variable cost remains a separate other-variable O&M
rate applied to **both** sides; it is not renamed or implicitly treated as wear.
If a previous all-in variable rate already covered fees/wear, remove those
components from that rate before supplying explicit fields. The software cannot
infer what a user's old all-in number meant. `realized_profit(..., battery=b)`
applies all fields; the old `variable_cost=` scalar remains supported, but using
both arguments raises an error to prevent double-counting.

`battery_economics.interval_net_profit` supplies the linear objective expression.
`account_dispatch` exposes independently reconciled historical cashflows.
Risk-neutral, CVaR and oracle solves use identical battery/cost assumptions.
The objective is expected **net** profit minus lambda times CVaR of scenario net
loss. Physical limits, binary operating mode, efficiencies, initial/final energy
and default dt=0.25 hours are preserved. Monthly comparisons require cyclic SOC
so idle is a feasible baseline. Arbitrary terminal SOC remains available in the
core optimizer; infeasible or nonoptimal solves raise, never score a bad schedule.

## Realized risk and compatibility

Loss is negative daily net profit. `commercial_summary` uses inverse empirical
CDF VaR and exact probability-mass CVaR:

```
VaR = sorted_losses[ceil(alpha * n) - 1]
CVaR = VaR + sum(max(loss - VaR, 0)) / (n * (1 - alpha))
```

Fractional boundary mass matters for small samples and ties. Negative VaR/CVaR
is valid when the loss tail is still profitable. Worst daily net loss is clipped
at zero; minimum signed daily profit is also reported. Standard deviation is
population (ddof=0). Drawdown is the largest fall from a running cumulative-P&L
peak, including the initial zero: the first day's loss is counted. No equity
capital is assumed, so drawdown is EUR, not a percentage. Profit per discharged
MWh is JSON null at effectively zero volume (<=1e-9 MWh).

Legacy monthly `summary`/`oracle` retain the historical interpolated-quantile
threshold-tail average for reproducing research evidence. New
`commercial_summary` and walk-forward metrics use the exact fractional-tail
definition, explicitly labeled. Do not compare the two CVaR columns as identical
estimators. Optimization-time scenario CVaR is a within-day distribution over
generated paths; empirical CVaR is across realized historical daily outcomes.

## Chronology and data quality

- `prepare` requires finite prices, valid unique timestamps and every expected
  quarter-hour over its observed Berlin delivery-date range. Partial boundary
  days, missing days and irregular intervals fail closed. Data errors abort;
  they are not silently turned into profitable eligible-day exclusions.
- Monthly APIs reject uncompleted calendar months and validate every interval
  in the target and preceding calibration month. UTC timestamps retain repeated
  local DST hours. Valid 92/100-slot DST days are logged and excluded because the
  daily residual/scenario implementation supports 96 slots only.
- Calibration forecasts train before the calibration month. Target models train
  before the target month. Residual folds remain anchored to February–August
  2026. This preserves the existing method, including its calibration weaknesses.
- Calendar and prior-day price summaries are chronologically lagged. The source
  has no verified archived publication timestamps/revision vintages. Therefore
  this is a delivery-date-controlled historical simulation, **not proof of
  day-ahead auction tradability**. No realized target-day label enters that
  day's forecasting inputs; later target days may use earlier published-price
  proxies. A production audit needs actual issue-time data.
- `evaluate_months` sorts daily rows, requires consecutive complete monthly
  reports, equal battery/cost/alpha/scenario assumptions, and one record or an
  explicit exclusion for every calendar date. Legacy reports without upstream
  metadata cannot establish forecast validity; the report says so. The explicit
  `require_complete=False` API option is solely for minimal synthetic fixtures,
  never enabled by the production CLI.

## Frozen selectors

The candidate grid remains lambda = 0, .25, .5, 1, 2. Both selectors use strictly
earlier evaluated months, optionally a fixed trailing month window. Ties choose
the lower lambda. The first month is selection-only in multi-month comparisons.

- `profit`: maximize total earlier net P&L (legacy rule).
- `net_downside`: maximize mean earlier daily net P&L minus
  `downside_penalty * max(0, empirical loss CVaR)`. Clipping avoids rewarding
  negative loss CVaR as though it were a positive risk cost.

Freeze the rule, penalty, candidate grid and all sensitivity assumptions before
target-period evaluation. The target month's outcomes never determine its lambda.
With one month, selection is pending: charts compare a **prespecified lambda=1**
against lambda=0, idle and oracle, while JSON retains all five candidate policies.
Do not interpret the best sensitivity row as an independently validated strategy.

## Controlled robustness

`config/commercial.example.json` lists one-at-a-time fees, discharge degradation,
round-trip efficiency, selector, scenario count and uncertainty width experiments,
plus a separately labeled joint stress. A round-trip efficiency override splits
symmetrically as eta_charge=eta_discharge=sqrt(RTE). Economic changes reuse the
same seeded paths; scenario counts use the same seed with the requested bootstrap
sample size. Dispatch is re-optimized for every case, including the oracle.

Uncertainty-width stress scales generated paths around their forecast mean;
realized prices remain unchanged. It is **not** an observed alternative market
regime or a profitability forecast. Separately, realized-volatility strata use
daily price standard deviation compared with the 25th/75th percentiles computed
from strictly earlier training days. Target-day regime labels are ex-post
diagnostics only, not forecasting or selection inputs. Empty strata are absent,
not imputed. Sparse regimes cannot establish robustness.

High-cost cases report idle days and negative historical days. Idle superiority
on realized losses is a hindsight observation; high predicted costs can instead
make zero dispatch optimal before the price is observed.

## Reproduction and provenance

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m scripts.run_commercial_backtest --history input/prices.csv --config config/zero_cost.json --output-dir output/zero_cost
python -m scripts.run_commercial_backtest --history input/prices.csv --config config/commercial.example.json --output-dir output/commercial
# Only after November ends and its complete source history is validated:
python -m scripts.run_commercial_backtest --history input/extended_prices.csv --first-month 2026-10 --last-month 2026-11 --config config/commercial.example.json --output-dir output/walk_forward_commercial
# If history is unavailable, explicitly pending structure (no fabricated charts):
python -m scripts.run_commercial_backtest --pending --output-dir output/pending
# Independently verify saved schedules and cashflows against the same input:
python -m scripts.audit_commercial_results --results output/commercial/results.json --history input/prices.csv --output output/commercial/verification.json
```

Each run writes results.json, report.html and labeled SVG plots. Existing result
directories are rejected. JSON records input/config SHA-256, source attribution,
dependency versions, seed, execution time, Git revision/dirty state, complete
configuration, all schedules, component accounting, exclusions and cutoffs.
Source data remain ignored by Git; source licenses and attribution still apply.

The paired iid-day bootstrap is descriptive and ignores serial dependence.
Month-block intervals are withheld below three evaluated months. Neither the
bootstrap nor a 30-day tail statistic proves economic superiority. Fixed O&M,
capex, financing, taxes, outages, network limits, auxiliary load, intraday and
imbalance costs, auction acceptance and market impact are not implemented.
