# BESS — Risk-Aware Battery Dispatch Optimization

A reproducible Python research and portfolio project for **day-ahead battery energy storage system (BESS) arbitrage**, combining electricity-price scenario generation, mixed-integer linear programming (MILP), and Conditional Value at Risk (CVaR).

> **Status:** Research demonstration with automated tests and a completed October 2026 historical simulation. This is **not** a verified live trading system or a claim of commercial profitability. October 2026 was used during development and is **not** an untouched out-of-sample holdout.

## Commercial backtesting upgrade

The framework now asks whether battery arbitrage remains attractive after
explicit costs, whether CVaR dispatch improves realized downside performance,
and whether those conclusions survive chronological evaluation and sensitivity
analysis. It preserves the original MILP, scenario method and October evidence.

- Separate purchase/sale fees, execution costs, legacy variable O&M and linear
  degradation per grid-side MWh discharged enter **every** optimization and
  historical evaluation with matching definitions. Defaults remain zero.
- Daily component reconciliation, throughput, net profit per discharged MWh,
  exact-tail empirical VaR/CVaR, negative-day frequency and drawdown accompany
  zero dispatch, risk-neutral, CVaR and unattainable oracle comparisons.
- Complete-month and quarter-hour checks reject missing or uncompleted history.
  Risk-weight selection can use earlier total profit or earlier mean net profit
  minus a prespecified downside penalty; target months never select themselves.
- JSON sensitivity configurations re-optimize dispatch for economic, efficiency,
  scenario-count and uncertainty assumptions. One-at-a-time experiments and
  joint stresses are labeled separately. Reports include observed volatility
  strata with thresholds calculated from earlier data.
- HTML reports and SVG charts are built from executed outputs, with input hashes,
  versions, seeds, exclusions and sample-size limitations. No source publication
  vintages are verified, so chronological simulation is not proof of auction
  tradability. No completed November 2026 result is claimed.

See [commercial methodology](docs/COMMERCIAL_METHODOLOGY.md),
[repository audit](docs/COMMERCIAL_AUDIT.md) and
[technical change log](docs/COMMERCIAL_CHANGELOG.md).

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -t . -v
python -m scripts.run_commercial_backtest --history input/prices.csv --config config/zero_cost.json --output-dir output/zero_cost
python -m scripts.run_commercial_backtest --history input/prices.csv --config config/commercial.example.json --output-dir output/commercial
```

Both commands default to October 2026, a **development** evaluation. Supply a
complete validated source CSV including earlier training history. The example
commercial values are illustrative assumptions, not actual tariffs or verified
asset costs. With only one month, the displayed risk-aware policy is prespecified
lambda=1; prior-month-selected evaluation remains pending. Existing output
directories containing results are protected from overwrite.

## Commercial results in pictures

**October 2026 development simulation: 30 eligible days, not live revenues.**
The figures below use the [executed results](docs/commercial_results/summary.json)
from the original Energy-Charts / Bundesnetzagentur DE-LU history. Costs are
illustrative; 25 October is excluded because of the DST transition.

### From gross arbitrage to net profit

![Gross-to-net cost reconciliation for risk-neutral and fixed-lambda CVaR dispatch](docs/commercial_results/gross_to_net.svg)

Risk-aware dispatch earned slightly less gross arbitrage profit but traded less
energy and incurred lower costs. Net P&L was **EUR 4,956.47**, compared with
**EUR 4,787.02** for risk-neutral dispatch under the same assumptions.

### Downside risk, trading activity and uncertainty

![Drawdown, historical loss CVaR, discharged energy and bootstrap uncertainty](docs/commercial_results/risk_and_uncertainty.svg)

The observed downside metrics were lower for fixed lambda=1, but the confidence
interval for its mean profit advantage includes zero. **Superiority is not
established.** The bootstrap ignores serial dependence and uses only 30 days.

### How profit accumulated

![Cumulative simulated net profit across October delivery days](docs/commercial_results/cumulative.svg)

The oracle knows future prices and is an unattainable hindsight reference.
See the [daily-profit and drawdown charts](docs/COMMERCIAL_RESULTS.md#realized-daily-risk)
for individual loss days and peak-to-trough changes.

### When the economics become unattractive

![Re-optimized net profit under cost, efficiency and uncertainty assumptions](docs/commercial_results/sensitivity.svg)

The joint cost/efficiency stress produced a loss; prohibitive degradation costs
made zero dispatch optimal on all 30 days. The selector comparison remains
pending because only one complete evaluation month is available.

To regenerate the two summary figures from the committed numerical evidence:

```bash
python -m scripts.plot_commercial_summary
```

## Project at a glance

| Component | Implementation |
| --- | --- |
| Market data | Historical 15-minute DE-LU day-ahead electricity prices |
| Scenario generation | Quantile gradient-boosting models and historical daily residual bootstrap |
| Optimization | Battery charge/discharge MILP formulated in Pyomo and solved with HiGHS |
| Risk | CVaR-based downside-risk objective with configurable risk weight |
| Evaluation | Historical realized-profit simulation, risk-neutral baseline, and perfect-foresight oracle |
| Engineering | Python unit tests, GitHub Actions, validated data pipeline, reproducible JSON reports |

## Why this project?

Day-ahead electricity prices are uncertain when battery schedules must be selected. A deterministic dispatch policy can appear profitable under perfect price foresight but be unrealistic in practice. This project generates multiple plausible price paths, optimizes a feasible battery schedule under those scenarios, and examines how the CVaR risk weight affects simulated realized profit and downside exposure.

The objective is to demonstrate a **complete quantitative workflow**—from market data through forecasting, constrained optimization, evaluation, and automated testing—rather than to claim deployment readiness.

## Methodology

1. **Historical data:** Validate a continuous, timestamped 15-minute DE-LU price history. Reject missing values, duplicate timestamps, and irregular intervals.
2. **Price scenarios:** Train quantile gradient-boosting models on historical dates and combine their estimates with bootstrapped full-day residual profiles to produce 50 price scenarios per eligible delivery day.
3. **Battery optimization:** Use a Pyomo MILP with charge/discharge power limits, energy balance, charging and discharging efficiencies, state-of-charge limits, and daily terminal-energy constraints.
4. **Risk-aware dispatch:** Compare risk weights `lambda = 0, 0.25, 0.5, 1, 2` using a CVaR formulation. The risk-neutral configuration (`lambda = 0`) is a baseline.
5. **Historical evaluation:** Evaluate fixed schedules against observed prices after optimization. Compare with a perfect-foresight **oracle**, which is an unattainable upper-bound reference, not a tradable strategy.
6. **Walk-forward protocol:** Train and calibrate each target month's scenario model using strictly earlier dates. Select the next month's risk weight using only earlier evaluated months. The multi-month workflow is implemented but has **not yet produced a verified multi-month empirical result**.

The scenario and dispatch workflows currently exclude days with other than 96 quarter-hour delivery intervals, including daylight-saving transition days. These exclusions are reported.

## Battery assumptions

The example system is **illustrative**, not a verified physical asset:

| Parameter | Value |
| --- | ---: |
| Energy capacity | 2 MWh |
| Charge/discharge power | 1 MW |
| Charging efficiency | 95% |
| Discharging efficiency | 95% |
| Initial and terminal state of charge | 1 MWh |
| Variable operating cost | 0 EUR/MWh (simplification) |

The optimization enforces a cyclic daily state of charge rather than interday carryover. Configurable fees and linear discharge degradation are now represented. Imbalance costs, availability, network constraints and nonlinear aging remain outside the model.

## Mathematical formulations

The optimization in [`src/battery_optimization.py`](src/battery_optimization.py) is a **single-stage, nonanticipative battery-dispatch MILP**. Both formulations select one day-ahead charge/discharge schedule. The stochastic model **does not** permit scenario-dependent recourse; uncertainty enters only through the scenario-dependent profit and the objective.

### Sets and indices

| Symbol | Definition |
| --- | --- |
| $`\mathcal{T}=\{0,\ldots,N-1\}`$, $`t`$ | Dispatch intervals; the default is 96 quarter-hour intervals on a regular delivery day. |
| $`\mathcal{E}=\{0,\ldots,N\}`$ | Energy-state boundaries, including the initial and final states. |
| $`\mathcal{S}=\{1,\ldots,K\}`$, $`s`$ | Finite electricity-price scenarios; the deterministic case has one price trajectory. |

### Parameters

| Symbol | Units | Meaning / implementation |
| --- | --- | --- |
| $`\Delta t`$ | h | Interval duration; default $`0.25`$. |
| $`\bar P`$ | MW | Common maximum charging and discharging power (`power_mw`). |
| $`\bar E`$ | MWh | Maximum stored energy (`capacity_mwh`); minimum is zero. |
| $`\eta_c,\eta_d`$ | dimensionless | Charging and discharging efficiencies in $`(0,1]`$. |
| $`E^{\mathrm{init}}`$ | MWh | Prescribed initial stored energy (`initial_mwh`). |
| $`E^{\mathrm{term}}`$ | MWh | Prescribed final stored energy (`terminal_mwh`), defaulting to $`E^{\mathrm{init}}`$. |
| $`c^{\mathrm{var}}`$ | EUR/MWh | Operating cost per MWh charged **plus** per MWh discharged (`variable_cost_eur_mwh`). |
| $`c^c`$ | EUR/MWh charged | Legacy variable O&M + purchase fee + execution cost. |
| $`c^d`$ | EUR/MWh discharged | Legacy variable O&M + sale fee + execution cost + discharge degradation. |
| $`\pi_{s,t}`$ | EUR/MWh | Electricity price at interval $`t`$ in scenario $`s`$. |
| $`w_s`$ | dimensionless | Scenario probability: $`w_s\ge 0`$, $`\sum_s w_s=1`$; uniform $`1/K`$ by default. |
| $`\bar\pi_t`$ | EUR/MWh | Mean scenario price used by the `deterministic()` wrapper: $`K^{-1}\sum_s\pi_{s,t}`$, **unweighted** even if scenario probabilities are separately supplied. |
| $`\alpha`$ | dimensionless | CVaR confidence level, $`0<\alpha<1`$, default $`0.95`$. |
| $`\lambda`$ | dimensionless | Nonnegative weight on CVaR of **loss**, default $`0`$ in `build_model()`; `stochastic()` defaults to $`1`$. |

### Decision variables

| Symbol | Domain | Meaning |
| --- | --- | --- |
| $`p_t^c`$ | $`[0,\bar P]`$ MW | Charging power at time $`t`$. |
| $`p_t^d`$ | $`[0,\bar P]`$ MW | Discharging power at time $`t`$. |
| $`u_t`$ | $`\{0,1\}`$ | Operating-mode indicator: 1 permits charging; 0 permits discharging. |
| $`e_t`$ | $`[0,\bar E]`$ MWh | Stored energy at boundary $`t`$, for $`t\in\mathcal E`$. |
| $`\zeta`$ | EUR, unrestricted | Auxiliary VaR threshold for scenario **loss**, created only when $`\lambda>0`$. |
| $`\xi_s`$ | EUR, nonnegative | CVaR excess loss for scenario $`s`$, created only when $`\lambda>0`$. |

### Shared physical MILP constraints

For every $`t\in\mathcal T`$:

```math
\begin{aligned}
0 &\le p_t^c \le \bar P u_t, \\
0 &\le p_t^d \le \bar P(1-u_t), \\
e_{t+1} &= e_t + \Delta t\left(\eta_c p_t^c-\frac{p_t^d}{\eta_d}\right), \\
0 &\le e_t \le \bar E, \qquad u_t\in\{0,1\}.
\end{aligned}
```

The energy bound also applies at $`t=N`$. Boundary conditions are

```math
e_0=E^{\mathrm{init}},\qquad e_N=E^{\mathrm{term}}.
```

The binary mode prevents simultaneous charging and discharging. A single set of $`p_t^c,p_t^d,u_t,e_t`$ variables is shared across **all** price scenarios: there are no scenario-indexed dispatch variables or post-realization decisions. The model includes explicit linear commercial costs; ramp limits, nonlinear aging and network limits remain omitted.

### 1. Deterministic MILP (one forecast price path)

Let $`\hat\pi_t`$ be the price trajectory known to the optimizer. For the `deterministic(scenarios, battery)` entry point, $`\hat\pi_t=\bar\pi_t`$ is the arithmetic mean of the supplied scenario prices. For `perfect_foresight(realized_prices, battery)`, the same deterministic MILP is solved **ex post** with realized prices as an unattainable oracle.

```math
\boxed{
\max_{p^c,p^d,u,e}\;
\sum_{t\in\mathcal T}\Delta t
\left[
\hat\pi_t(p_t^d-p_t^c)
-c^c p_t^c-c^d p_t^d
\right]
}
```

Subject to **all shared physical constraints** above. Price and cost are in EUR/MWh and power times hours gives MWh, so the objective is in EUR. The deterministic wrapper uses a single trajectory and no CVaR term by default; it is **not** a claim that the future price is known.

### 2. Stochastic risk-aware MILP (fixed schedule across scenarios)

For each $`s\in\mathcal S`$, scenario profit and loss are

```math
\Pi_s =
\sum_{t\in\mathcal T}\Delta t
\left[
\pi_{s,t}(p_t^d-p_t^c)
-c^c p_t^c-c^d p_t^d
\right],
\qquad L_s=-\Pi_s.
```

The expected profit is $`\mathbb E[\Pi]=\sum_s w_s\Pi_s`$. CVaR of **loss** is represented by the Rockafellar–Uryasev linearization:

```math
\begin{aligned}
\mathrm{CVaR}_{\alpha}(L)
&=\zeta+\frac{1}{1-\alpha}\sum_{s\in\mathcal S}w_s\xi_s,\\
\xi_s&\ge -\Pi_s-\zeta,\quad
\xi_s\ge0 \qquad (s\in\mathcal S).
\end{aligned}
```

The implemented risk-aware MILP is

```math
\boxed{
\max_{p^c,p^d,u,e,\zeta,\xi}
\left\{
\sum_{s\in\mathcal S}w_s\Pi_s
-\lambda\left(
\zeta+\frac{1}{1-\alpha}\sum_{s\in\mathcal S}w_s\xi_s
\right)
\right\}
}
```

subject to the **shared physical constraints** and CVaR excess-loss constraints above, with $`\lambda>0`$. Because $`\zeta`$ and $`\xi_s`$ enter a maximization objective with a negative CVaR coefficient, the model minimizes the tail-loss expression as part of optimizing dispatch. At $`\lambda=0`$, the code **omits** the CVaR auxiliary variables and maximizes expected profit alone:

```math
\max_{p^c,p^d,u,e}\;\sum_{s\in\mathcal S}w_s\Pi_s.
```

This risk-neutral objective is equivalent to a deterministic optimization using the **probability-weighted** mean price $`\sum_s w_s\pi_{s,t}`$. It coincides with the `deterministic()` arithmetic-mean wrapper when probabilities are uniform. For $`\lambda>0`$, the model remains a MILP: the battery dynamics and profit expressions are linear, CVaR is linearized, and $`u_t`$ is binary.

### Implementation correspondence and interpretation

- `build_model()` creates `m.T`, `m.E`, `m.S`, `m.charge`, `m.discharge`, `m.mode`, `m.energy`, `m.profit`, `m.expected_profit`, and (only for positive risk weight) `m.var_loss`, `m.excess_loss`, `m.tail`, and `m.cvar_loss`.
- `deterministic()` optimizes a mean price path; `stochastic()` optimizes one **common** schedule against all scenario paths; `perfect_foresight()` is a hindsight reference, not a day-ahead strategy.
- The reported CVaR objective is a **scenario-distribution tail-loss penalty on one day's profit**. The separate empirical CVaR of **daily realized losses** in the October results is an evaluation statistic, not the optimization variable itself.
- Typical demonstration settings: $`N=96`$, $`K=50`$, $`\Delta t=0.25`$ h, $`\alpha=0.95`$, and $`\lambda\in\{0,0.25,0.5,1,2\}`$. The number of intervals/scenarios is determined by the supplied price array, not hard-coded in the MILP.


## Executed commercial rerun — October 2026 development data

The upgrade was executed on the original price artifact for 30 eligible days,
with 11 illustrative commercial configurations. The base case uses purchase
and sale fees of 1 EUR/MWh each, execution cost of 0.5 EUR/MWh on each side,
discharge degradation of 10 EUR/MWh, and zero legacy O&M.

| Strategy | Simulated net P&L EUR | Empirical 95% loss CVaR EUR |
| --- | ---: | ---: |
| Zero dispatch | 0.00 | 0.00 |
| Risk-neutral | 4,787.02 | 38.90 |
| CVaR, prespecified lambda=1 | 4,956.47 | 24.88 |
| Unattainable oracle | 8,741.97 | -75.50 |

These new risk statistics use exact fractional-tail CVaR. The paired iid-day
95% interval for the mean lambda=1 minus risk-neutral net-P&L difference was
**[-0.27, 12.28] EUR/day**, which includes zero and ignores serial dependence.
The joint cost/efficiency stress yielded losses for both policies; prohibitive
degradation costs led to zero dispatch on all 30 days. No general profitability
or risk-aware superiority is established.

**Validation:** 88 automated tests passed. Independent checks reconciled 2,310
commercial and 210 zero-cost schedules against the source prices and physical
constraints. Multi-month empirical selection remains pending; November is
incomplete. See [executed results, charts and limitations](docs/COMMERCIAL_RESULTS.md).

## Original historical results — October 2026 (preserved)

The end-to-end monthly scenario and optimization pipeline was executed on **30 eligible delivery days**. October 25 (daylight-saving transition, 100 intervals) was excluded. September 2026 was used for scenario calibration.

| CVaR risk weight (lambda) | Simulated total profit (EUR) | Empirical CVaR of daily loss (EUR) |
| ---: | ---: | ---: |
| 0 | 6,308.94 | 20.29 |
| 0.25 | 6,204.00 | 12.65 |
| 0.5 | 6,238.28 | 13.21 |
| 1 | 6,368.11 | 9.67 |
| 2 | 6,371.48 | -1.49 |
| Perfect-foresight oracle | 10,409.79 | -129.37 |

**Interpretation:** These are *simulated gross arbitrage results* for the illustrative battery, not realized revenues. Choosing the best risk weight after inspecting October outcomes would bias any claim of independent October performance. CVaR estimated from only 30 daily observations is particularly unstable. The oracle is not operationally achievable.


## October 2026 evaluation charts

The following charts visualize the documented October experiment for an illustrative 2 MWh / 1 MW battery. They use the aggregate figures in [ROLLING_OCTOBER_RESULTS.md](docs/ROLLING_OCTOBER_RESULTS.md), not newly generated dispatch or price time series.

![Simulated gross arbitrage profit by CVaR risk weight](docs/figures/october_profit.svg)

![Empirical CVaR of daily loss by risk weight](docs/figures/october_cvar.svg)

**Reading the charts:** Results cover 30 eligible October 2026 days. They are exploratory simulated gross profits and empirical downside-risk estimates, not verified trading revenues. The 30-day CVaR estimates are unstable; selecting the best lambda from October outcomes would introduce hindsight bias. The perfect-foresight oracle is excluded from these policy-comparison charts because it is not a feasible trading strategy.

## Reproduce the project

Requires Python and the dependencies in `requirements.txt`, including Pyomo and the HiGHS solver.

```bash
python -m pip install -r requirements.txt
```

Provide a **complete, validated** historical 15-minute DE-LU price CSV, then run the single-month demonstration:

```bash
python battery_monthly_scenarios.py \
  --history output/extended_prices.csv \
  --month 2026-10 \
  --output output/october_demo.json \
  --seed 42
```

Replace `output/extended_prices.csv` with the actual path to the validated dataset. The command generates scenario diagnostics, dispatch schedules, per-day outcomes, and aggregate risk/profit results in JSON.

For a detailed execution guide, see [SINGLE_MONTH_DEMO.md](docs/SINGLE_MONTH_DEMO.md).

### Run automated tests

```bash
python -m unittest discover -s tests -t . -p "test_battery*.py"
python -m unittest tests.test_extend_price_history tests.test_run_battery_walk_forward
```


### Future multi-month evaluation

The [walk-forward protocol](docs/WALK_FORWARD_PROTOCOL.md) specifies monthly model cutoffs, prior-month risk-weight selection, data checks, and uncertainty reporting. Run it only when **at least two complete, validated evaluation months** are available. The November 2026 month must be complete before it can be included. No multi-month out-of-sample result is claimed at present.

## Repository layout

Core implementation lives in `src/`, unit and compatibility tests in `tests/`, command-line utilities in `scripts/`, and research notes and figures in `docs/`. Root-level Python files remain as backward-compatible import and command-line entry points so existing commands and GitHub Actions continue to work.

```text
src/       Battery models, scenario generation, and data validation
tests/     Unit, integration, and layout compatibility tests
scripts/   Command-line tools and workflow runners
docs/      Research methods, experiment results, and figures
```

## Key files

| File | Purpose |
| --- | --- |
| `src/scenarios.py` | Electricity-price scenario modeling |
| `src/battery_optimization.py` | Battery MILP and CVaR formulation |
| `src/battery_monthly_scenarios.py` | End-to-end monthly scenario generation and dispatch evaluation |
| `src/battery_walk_forward.py` | Prior-month risk-weight selection and walk-forward metrics |
| `scripts/run_battery_walk_forward.py` | Multi-month evaluation orchestration |
| `src/extend_price_history.py` | Historical data extension and validation |
| `docs/ROLLING_OCTOBER_RESULTS.md` | Documented October 2026 numerical results |
| `docs/WALK_FORWARD_PROTOCOL.md` | Prospective evaluation protocol |
| `.github/workflows/` | Continuous integration and evaluation workflows |

## Portfolio skills demonstrated

**Energy market analytics · Stochastic optimization · MILP · Pyomo · HiGHS · CVaR · Time-series modeling · Battery energy management · Python · Automated testing · Reproducible backtesting**

## Limitations and next steps

- Validate the workflow prospectively on additional complete months not used during development or tuning.
- Quantify forecasting calibration, profit uncertainty, and robustness across changing market conditions.
- Verify site-specific constraints and the implemented cost assumptions before considering real-world deployment; extend linear degradation to cycle-depth/calendar aging only with defensible asset inputs.
- Expand visual reporting with price scenarios, dispatch profiles, state of charge, and risk-return comparisons.

**Scope:** This repository demonstrates research and engineering methods. It does not provide investment advice, guaranteed returns, or a production trading system.

## License

This project's original source code is licensed under the [Apache License, Version 2.0](LICENSE). Third-party data and services retain their own terms and licenses.
