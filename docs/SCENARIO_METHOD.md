# BESS — approved DE–LU day-ahead research design (v0.5)


## Approved provisional operating assumptions (user decision, 2026-11-06)


- **Cyclic daily energy:** `E[T+1] = E[1]`; the common `E[1]` is **a decision variable** within the allowed energy window, rather than an imposed 50% SOC or a freely different final SOC. This is suitable for a **single-day mathematical sensitivity study** but must not be misrepresented as a reconstructable real operating schedule: a battery's initial energy at the bidding decision is physically given. A rigorous historical backtest should use a **fixed, observed or explicitly pre-committed common initial energy across all models**, or a chronological multi-day run that carries ending energy into the next day. The free-initial benchmark must be labeled as an *optimistic relaxed benchmark* and kept separate from realistic evaluation.
- **Degradation cost is conceptually distinct from O&M**. Keep `c_deg_ch` and `c_deg_dis` as separate parameters; their asset-specific numeric values are unknown. Do not silently infer from the O&M=0 setting that battery wear is zero. A first demonstration may deliberately set degradation to zero too **only if labeled as a separate assumption**.

## Goal and three strategies

Compare the **same battery** over historical Germany–Luxembourg (DE-LU) day-ahead delivery days. All live strategies act on information available **before the day-ahead auction**, not on future cleared prices.

1. **Deterministic (forecast-based)**: optimize one common 15-minute charge/discharge schedule using one point forecast. For comparability to the risk-neutral stochastic objective, use the **arithmetic expected price from the scenario ensemble** (not the median, which in general differs from the expectation).
2. **Stochastic (risk-aware)**: optimize one common, nonanticipative schedule against all weighted price paths; objective **maximize expected profit minus λ × CVaR of loss** at a chosen tail level (e.g. 95%, tunable). The schedule is the *same* in every price scenario because the auction price is not yet known when the decision is made. Scenarios affect the profit distribution and risk term, not which schedule gets submitted after the fact. At λ=0 and with linear price revenue, this collapses mathematically to strategy 1 with ensemble-mean prices.
3. **Perfect-foresight oracle**: retrospectively optimize a feasible schedule using **actual** cleared day-ahead prices. This is an optimistic reference/upper bound for the simplified scheduling model, **not a deployable pre-auction trading strategy**. It is not legitimate to claim an oracle schedule could have been bid at those already-revealed prices.

Real-world auction bids may be price-contingent and have more complex acceptance, clearing, and product constraints. v0.2 uses an explicitly simplified **price-taker, fixed pre-auction schedule** for an apples-to-apples educational benchmark. It does not simulate the auction clearing mechanism, execution risks, intraday corrections, or imbalance settlements.

## First real data check — GitHub Actions, verified 2026-11-06

- The run printed: **`100` valid intervals saved** for 2026-10-25 (Berlin fall-DST day); all six tests passed.
- Initial test failures were useful and **fixed**: compare DST timestamps in UTC and accept the actual API unit spelling `EUR / MWh` in addition to `EUR/MWh`.
- **Caution:** this success establishes access and schema/completeness for *one delivery day only*. It is not evidence that the entire proposed training/test period is available, complete, or free of revisions. Retrieve a longer history and test day-by-day before claiming a full backtest dataset.

## Full market-price history — completed GitHub Actions acquisition, 2026-11-06

- **Period:** 2025-10-01 through 2026-10-31 (Berlin delivery dates; a full 13 months). **38,020** 15-minute observations reported in logs.
- **Calendar checks:** each date is compared against its true Berlin-time 15-minute horizon: ordinary 96, fall-back 100, spring-forward 92. Price and timestamp nulls/duplicates are rejected. The combined CSV is sorted in UTC.
- **API rate limiting:** initial run failed with HTTP 429 in March 2026. The re-run used 15-second inter-request spacing and a controlled retry after one 429 for February; all months then passed and were stored.
- **Train/test split for next stage:** 2025-10 to 2026-09 for chronological model fitting and residual validation; 2026-10 **strictly held out** for performance measurement. Never use October 2026 prices to train or generate October pre-auction forecasts.
- **Important limitations:** the artifact contains **market price**, not actual site power/SOC; the program verifies coverage and structural validity but not official historical revisions, source licensing, forecasting leakage or dispatch behavior. No scenario generator or battery MILP has been executed yet.

## First scenario-generation run — executable prototype, calibration NOT accepted

- **Method:** sklearn quantile HGB regressors (q10/q50/q90), calendar + previously published prior-day DA price summaries as pre-auction features, four expanding temporal validation folds (Feb–Sep 2026), whole-day normalized out-of-sample error vectors resampled with seed 42. **241** usable ordinary-day residual trajectories were logged, with **50** equally weighted Monte Carlo draws for the held-out ordinary day 2026-10-15 (**96** intervals).
- **Critical empirical limitation:** q10–q90 validation coverage **0.502**, well below the **0.80 nominal** target. This shows **underestimated uncertainty/miscalibration**. The fact that CSV files were generated does **not** imply good probabilistic scenarios, accurate trading signals, or economically reliable stochastic optimization. Improve/validate calibration out of sample **before** making any performance/risk claims, especially tail CVaR; consider longer calibration windows, stronger ex-ante features, and/or calibrated residual scaling.
- **DST scope:** current scenario prototype intentionally rejects delivery days with 92 or 100 intervals; they are present in the raw dataset but not yet valid scenario targets. Do not silently force 96 intervals on DST days.
- **Data timing:** October 2026 prices are held out for training and residual pools; prior delivery-day **published day-ahead prices** can be available before the D-1 auction for the target. No same-day price enters features or the scenario output. Future tests must check publication/issue-time eligibility for every exogenous feature and retraining schedule.
- **Next quality gate:** demonstrate credible out-of-sample predictive interval coverage (near nominal, with an independently separated validation interval) and daily path dependence before relying on generated scenarios in the risk-aware MILP. The code's unit tests address mechanics, not statistical calibration.

## Scenario recalibration and genuine chronological October test — 2026-11-06

- **Before correction**, an earlier model's q10–q90 coverage was 50.2% on February–September expanding folds. In a revised February–August out-of-sample calibration set, raw coverage was **51.8%**, with an *in-calibration* conformal margin of **26.85 EUR/MWh** yielding **80.0%** on that **same** calibration set. *That 80% is not independent validation.*
- **September 2026 model-development diagnostic (30 normal days):** raw q10–q90 coverage **33.4%**; historical static margin **59.5%**; time-ordered, **past-30-day-only** conformal margin **74.8%**. The 50-scenario empirical p10–p90 band covered **66.0%** before separate scenario spread calibration. September was examined to revise the method, so it is **not an untouched test set**.
- **After September ended**, the method fixed (a) a **46.91 EUR/MWh** conservative interval margin calculated from September out-of-sample errors and (b) a **1.377** scenario spread multiplier calculated **only with September**. Both were fixed before October performance evaluation; no October actual prices went into the model fit or these factors.
- **Held-out October evaluation**, without refitting or revising calibration on October: **30 ordinary days (2,880 intervals)**, interval-bound coverage **77.1%**; scenario empirical p10–p90 coverage **74.4%**. These are *different* coverage metrics. The fall-DST delivery day **2026-10-25 (100 slots) was excluded** because current scenario implementation is limited to 96-slot days. There is no evidence here that full DST scenario scheduling works.
- **Interpretation:** moving calibration improved but did **not** establish reliable 80% marginal coverage, joint-path calibration, or trustworthy 95% CVaR risk estimates. The 50-scenario sample has only about 2–3 scenarios in a 95% tail; 74.4% observed marginal coverage is insufficient for risk assertions. **Do not label this a production-ready stochastic battery strategy.**
- **Output schema:** the CSV explicitly distinguishes `lower_calibrated`, `q50_forecast`, and `upper_calibrated` from the *sampled scenario* `scenario_p10` and `scenario_p90`. The calibrated bounds are **not automatically true 10th/90th conditional quantiles**. No actual held-out price labels are included in the scenario CSV. Data is from actual Energy-Charts DE–LU prices; the scenario *values are model-generated*, not observed market trajectories.

## October scenario price-tail audit — completed 2026-11-06, risk quality gate FAILED

- **Held-out period:** 30 ordinary October 2026 Berlin delivery days, **2,880 actual quarter-hour prices**, compared against **50 price-scenario trajectories per day**, with September-only calibration. 2026-10-25 (100 periods due to DST) excluded; no price from the October target date was used in generation before evaluation.
- **Interval scenario band:** empirical p10–p90 coverage **74.375%**; **4.271%** of realized prices fell below p10 and **21.354%** exceeded p90 (ideal tail split ~10% below, ~10% above). These are distinctly imbalanced, **not** merely a symmetric spread issue.
- **Negative prices:** **1 of 2,880 observed intervals** (0.0347%) was negative, while **13.619%** of generated scenario prices were negative. Beware log rounding to 0.000 in earlier version; count has been checked from the JSON and print precision corrected in subsequent source update.
- **Extremes relative to the PRE-OCTOBER training distribution:** historical marginal p05 **−0.02 EUR/MWh**, p95 **195.937 EUR/MWh**. Observed October exceeded that training p95 in **38.472%** of intervals vs **28.086%** of scenario prices; observed October fell below training p05 in **0%** vs **13.614%** of scenario prices. These thresholds are descriptive and entirely train-defined, **not** calibrated conditional price quantiles for October.
- **Daily price spread (daily max − daily min):** mean actual **176.075 EUR/MWh**, mean scenario daily spread **389.741 EUR/MWh**. In addition to excessive simulated daily amplitude, scenarios underpredict upper-side interval exceedances. The two features can coexist because calibration is misaligned / the forecast location may be biased.
- **Within-day adjacent 15-min autocorrelation:** mean actual **0.9615**, scenario **0.9395**. Correlation alone does not validate joint price paths or correct tails.
- **Next simple corrective direction:** inspect bias/market-regime changes; prefer chronological and seasonally relevant ex-ante conditioning; check upper vs lower calibration separately and avoid indiscriminately scaling both tails; expand scenario pool to improve CVaR-tail resolution; keep October as an evaluation slice instead of refitting ad hoc on its outcomes.

## Actual market data and timestamps

- Bidding zone: **DE–LU**; settlement price **EUR/MWh**.
- Day-ahead resolution from 2025-10-01 is **15-minute MTU**: normally 96 slots/day. Treat timestamps as timezone-aware `Europe/Berlin`; DST changeover days can contain 92 or 100 slots (October 25, 2026 has 100). Define the optimizer horizon dynamically instead of assuming 96 always.
- Data candidate: Fraunhofer ISE Energy-Charts API `https://api.energy-charts.info/v2/price?bzn=DE-LU&start=2026-10-01&end=2026-10-31`; the **one-day** endpoint/schema was successfully tested with GitHub Actions on 2026-11-06; **full-period** coverage and possible API revisions still require checking. Retain source and licensing attribution.
- For initial backtest: hold out **October 2026**. Fit parameters only using past data, e.g. Oct 2025–Sep 2026, then test day-by-day on Oct 2026 in a reproducible out-of-sample procedure. The tested day must never appear in fitted features, residuals, or calibration data.
- Use only ex-ante-known covariates at forecast issue time: calendar, eligible lagged day-ahead prices, and if accessible *archived forecasts* for wind, solar and load. **Do not leak actual next-day demand or generation.**

## Scenario generator — primary approach: quantile regression + trajectory residual bootstrap

Target: ~**50 complete day-ahead price-path scenarios** per delivery day, with initially equal probabilities (2% each) and optionally a time-valid weighting scheme.

1. **Data engineering** using `pandas` and `numpy`: align prices on timezone-aware 15-minute delivery timestamps, and construct features available before the auction. Handle DST and missing slots explicitly.
2. **Chronological training/validation**: fit a consistent `scikit-learn` pipeline only on prior days. Use rolling-origin or temporally separated validation; fit preprocessing/scaling on each training fold only.
3. **Quantile regression**: use `sklearn.ensemble.HistGradientBoostingRegressor(loss="quantile", quantile=q)` for q = 0.10, 0.50, 0.90, with a small, transparently tuned hyperparameter grid. Check quantile crossing and recalibrate on prior held-out dates.
4. **Honest daily residuals**: obtain historically *out-of-sample* predictions, then compute complete daily residual vectors `r[d,t] = actual_price[d,t] - predicted_median[d,t]`. Never build residual samples from in-sample fitted residuals.
5. **Scale by conditional uncertainty**: if used, scale positive residuals by historical upper predicted spread (`q90-q50`) and negative residuals by lower spread (`q50-q10`); use minimum positive denominators and safe handling for quantile crossing. Reapply target-day conditional spread on reconstruction. This is an approximation requiring empirical calibration.
6. **Whole-day bootstrap**: sample 50 past *daily residual vectors* (optionally conditioned on similar features/market regime) **as blocks**, not slot-by-slot independently. Apply the target day median and spreads to each vector. A whole-day block better preserves intraday residual autocorrelation, spikes and negative-price sequences. It does **not** by itself guarantee correct scenario dependence or calibration.
7. **DST**: never add 96-length residuals to 100-length price paths. Use a defined DST-aware matching/alignment scheme or analyze DST dates separately and label exclusions.
8. **Scenario output**: matrix `prices[scenario, interval]` and nonnegative weights `probabilities[scenario]` summing to one; store forecast issue time, data cutoff, random seed, and source version.

Keep K-nearest-neighbour historical analogue days as an **optional later forecasting benchmark**, not as a component of the accepted main pipeline. Independent Gaussian noise at every quarter-hour is a poor benchmark because it destroys the path dependence.

## Mathematical optimization problem — explicit three-model formulation

**Scope and decision timing.** This first version studies a *price-taking, pre-auction fixed physical schedule* for the Germany–Luxembourg day-ahead market. The quantities chosen before the auction must be identical across all price scenarios. **This is a scheduling benchmark, not yet a simulation of limit orders, auction acceptance, or actual market settlements.** Later we can separately implement price-contingent bids and the associated market mechanism.

### Sets, parameters, and units

- `t ∈ {1,…,T}`: 15-minute delivery intervals in one local delivery day (`Δt = 0.25` h). Normally `T = 96`; DST days use their actual 92/100 slots.
- `s ∈ {1,…,S}`: price scenarios; initial target `S=50`.
- `p[s,t]`: forecast scenario day-ahead price (EUR/MWh). `w[s] ≥ 0`, `Σ_s w[s] = 1` (initially equal weights).
- `p_actual[t]`: actual cleared day-ahead price, used **only after the fact** for evaluation and the oracle.
- `Pmax`: symmetric charge/discharge power rating (MW). Separate charge/discharge limits are easy extensions.
- `Emax`: usable energy capacity (MWh), and `Emin`: lower allowable energy bound (MWh).
- `ηc, ηd ∈ (0,1]`: charging and discharging efficiencies (not round-trip efficiency inserted twice).
- `E0`: shared daily initial and terminal energy decision variable (MWh) for the relaxed single-day experiment, `E[1] = E[T+1] = E0`, `Emin ≤ E0 ≤ Emax`. This is **not** measured initial SOC; see approved-assumptions caveat for real backtests.
- `c_vom_ch, c_vom_dis`: **variable maintenance/O&M** rates, provisionally **0 EUR/MWh** for each direction. `FOM_daily`: **fixed O&M** allocation, provisionally **0 EUR/day**. `c_deg_ch, c_deg_dis`: distinct battery degradation/wear charges (EUR/MWh of AC throughput), **not yet quantified**; do not double count them.
- `α ∈ (0,1)`: CVaR confidence level; `λ ≥ 0`: dimensionless risk-aversion weight. These are *design parameters* to be chosen and disclosed, **not estimates from market data**.

### Common first-stage decision variables

- `ch[t] ≥ 0`: charging power (MW).
- `dis[t] ≥ 0`: discharging power (MW).
- `E[t]`: stored energy at the beginning of interval `t` (MWh), with `E[T+1]` after the final interval. Its initial value `E0=E[1]` is **optimized** in the relaxed daily benchmark subject to the cyclic equality.
- `u[t] ∈ {0,1}`: charging/discharging exclusivity indicator; `u=1` allows charging, `u=0` allows discharging.
- In the risk model only: `ζ ∈ ℝ`, a free loss threshold (VaR auxiliary variable), and `z[s] ≥ 0`, each scenario's excess loss above `ζ`.

**All** `ch[t], dis[t], E[t], u[t]` are **shared across scenarios** (nonanticipativity). The stochastic model must NOT use `ch[s,t]` or `dis[s,t]` selected after observing the day-ahead price.

### Common physical constraints (apply to all three models)

For every `t = 1,…,T`:

```text
0 ≤ ch[t]  ≤ Pmax * u[t]
0 ≤ dis[t] ≤ Pmax * (1-u[t])
u[t] ∈ {0,1}

E[t+1] = E[t] + ηc*ch[t]*Δt - (dis[t]/ηd)*Δt

Emin ≤ E[t] ≤ Emax                    for t=1,…,T+1
E[1]   = E0
E[T+1] = E0
Emin ≤ E0 ≤ Emax                       (E0 is optimized here)
```

The binary `u[t]` prevents simultaneous charge and discharge, including pathological cycles that can arise under negative spot prices. The bounds and energy balance have consistent MW/MWh/hour dimensions. **For operational or walk-forward realized-profit evaluation, replace the optimized E0 by a physical measured/pre-committed initial state (or chronological cross-day SOC carryover), identically for A, B, and C.** A valid starting example is a 2-hour battery (`Emax/Pmax = 2 h`), but the actual numeric battery specification **has not yet been approved**.

Optional future constraints: cycle/throughput limit, availability windows, ramp constraints, grid import/export limits, battery degradation curve, or reserve capacity. Do **not** present them as implemented yet.

### Revenue and profit under a given price path

For **any** price vector `p[t]`, define

```text
Profit_operating(ch, dis | p)
 = Σ_(t=1)^T Δt * [ p[t]*(dis[t]-ch[t])
                    - c_vom_ch*ch[t] - c_vom_dis*dis[t]
                    - c_deg_ch*ch[t] - c_deg_dis*dis[t] ]       [EUR]

Profit_net(ch,dis | p) = Profit_operating(ch,dis | p) - FOM_daily

Provisional O&M only: c_vom_ch = 0, c_vom_dis = 0, FOM_daily = 0.
Degradation cost terms are independent and still require specification.
```

Positive `dis-ch` sells energy; negative `dis-ch` purchases energy. With a **negative** price, buying energy can create positive price revenue, but still consumes physical capacity and incurs any throughput cost. Use `Π[s] = Profit_net(ch,dis | p[s,:])` consistently in all three objectives. Fixed O&M is zero in the approved initial run; if later set nonzero it changes reported net margins but is schedule-invariant for this short horizon.

### Model A — Deterministic (forecast-based MILP)

Let the point forecast equal the **probability-weighted ensemble mean**

`p_mean[t] = Σ_s w[s] p[s,t]`.

Choose the common power schedule and SOC to solve

```text
maximize   Profit(ch,dis | p_mean)
subject to all common physical constraints
```

The same forecast-origin and inputs must be used for the stochastic model. A median forecast is a different point forecast; using it here would confound risk with the forecast choice.

### Model B — Stochastic risk-aware (mean–CVaR MILP)

Minimize *downside losses* by incorporating `CVaR_α(L)` where scenario loss is `L[s] = -Π[s]`; profit is scenario-dependent only through the ex-ante uncertain prices.

Use the exact linear CVaR epigraph:

```text
maximize   Σ_s w[s]*Π[s]
           - λ * ( ζ + [1/(1-α)] * Σ_s w[s]*z[s] )

subject to all common physical constraints
           z[s] ≥ -Π[s] - ζ           for every scenario s
           z[s] ≥ 0                   for every scenario s
           ζ free (can be positive or negative)
```

When `λ=0`, the stochastic objective reduces **exactly** to the deterministic objective with `p_mean`, assuming matching costs and constraints. **Therefore a difference between Models A and B requires risk aversion, valid recourse, or other nonlinear/price-contingent market features.** For the initial comparison we use `λ>0` and no recourse.

With 50 equally weighted scenarios, an `α=0.95` tail contains only about 2–3 scenarios, making CVaR estimates noisy. Prefer a sensitivity analysis including `α=0.90` (about five tail scenarios) and/or more scenarios, with seeds and validation reported. `λ` must be selected before the held-out test or on a **separate** validation interval; never tune it on October outcomes.

### Model C — Perfect-foresight MILP (evaluation oracle only)

After delivery, solve

```text
maximize   Profit(ch,dis | p_actual)
subject to exactly the same common physical constraints
```

This is the **idealized upper bound on realized profit in this fixed-schedule model** for each individual delivery day. It is not an actionable pre-auction strategy; it deliberately sees the actual price that Models A/B cannot know.

### Realized out-of-sample comparison

For each held-out day `D`, calculate the pre-auction schedules `x_A(D)` and `x_B(D)`, then evaluate **both fixed schedules** at the *same realized* `p_actual(D)`. Solve the oracle only afterward.

```text
realized_A[D] = Profit(x_A(D) | p_actual(D))
realized_B[D] = Profit(x_B(D) | p_actual(D))
oracle[D]     = max_x Profit(x | p_actual(D))
regret_A[D]   = oracle[D] - realized_A[D]
regret_B[D]   = oracle[D] - realized_B[D]
```

Report realized total/mean profit, lower-tail outcomes and CVaR across evaluation days, scenario calibration, SOC profiles, number of cycles/throughput, and regret relative to the oracle. The regret is nonnegative **only under exactly identical feasible sets and cost assumptions**, which is why the same constraints and costs are crucial.

**Solver classification:** because `u[t]` is binary and all remaining expressions are linear, all three problems are **mixed-integer linear programs (MILPs)**. `scikit-learn` is used for price forecasts, *not* for the battery optimization. A MILP-capable solver (e.g., SciPy's `scipy.optimize.milp` backed by HiGHS, or a similarly documented alternative) is required in addition to NumPy, Pandas and Matplotlib.

### Pending numerical specification (intentionally not invented)

Before implementing, choose and record `Pmax, Emax, Emin, ηc, ηd, c_deg_ch, c_deg_dis, α, λ`, the solver, and the actual measured/precommitted E0 needed for *operationally valid* backtests. **Already provisionally set by user:** cyclic relaxed daily boundary `E[1]=E[T+1]=E0` with optimized E0; variable O&M both zero; fixed O&M daily zero. Until those are confirmed, **no computed dispatch or performance results exist**.


## Industrial practice audit — operational and commercial realism (2026-11-06)

**Evidence basis:** NREL/US National Laboratory System Advisor Model (SAM) battery dispatch, cell/system losses and lifecycle documentation; 2025 Annual Technology Baseline (ATB) utility-scale battery assumptions; and published battery dispatch mathematical formulations. These are **public engineering references and not verified confidential settings of any particular German BESS operator**. Confirm actual limits, warranties, costs, and grid contracts from the project's EPC/PCS/BMS and trading arrangements.

### A. State variables: SOC vs SOE — do not conflate without a model definition

- **SOE (state of energy)**: energy stored, `E[t]`, in **MWh**; define energy percentage `SOE_frac[t] = E[t] / E_available[t]`.
- **SOC (state of charge)**: electrochemical charge-state fraction normally in **%**, tracked by the BMS. It need not be numerically identical to energy fraction when voltage/usable capacity depend on state or temperature.
- In the **simple linear optimization** we explicitly **approximate SOC and normalized SOE as equal**, using `soc[t] := E[t] / E_available` with constant available capacity for a day. This is a modeling approximation, **not** an electrochemical identity.
- Define `soc_min` and `soc_max` and convert to energy bounds on a consistent capacity basis, e.g., `Emin=soc_min*E_available`, `Emax=soc_max*E_available`. **For the user-approved relaxed one-day benchmark** set `soc_initial = soc_final` but let their common value be optimized within those bounds. This is **not** an observed initial SOC or a physical pre-auction decision. The hardware's nameplate energy rating and the **usable** energy between SOC limits are different quantities.
- Preserve `E[t]` across consecutive days in multi-day simulations; do not freely reset SOC each morning. For a **one-day independent benchmark only**, impose `E[T+1]=E[1]`, and for the **relaxed** benchmark here let the common value be optimized. Even this cyclic condition does not make free-initial energy physically available at the start of a real trading day. A multi-day rolling horizon should carry SOC forward; realistic out-of-sample comparisons need an exogenously known initial state.

### B. Charge/discharge limits and energy balance (essential for v1)

All `ch[t]` and `dis[t]` below are **AC power at the battery power-conversion system (PCS) terminals** (MW). Conversion efficiency `ηc` is AC-to-stored-energy and `ηd` is stored-energy-to-AC, so **do not subtract PCS losses a second time**.

```text
0 ≤ ch[t]  ≤ available[t] * P_charge_max[t] * u[t]
0 ≤ dis[t] ≤ available[t] * P_dis_max[t] * (1-u[t])
u[t] ∈ {0,1}
E[t+1] = E[t] + Δt*(ηc*ch[t] - dis[t]/ηd)
Emin[t] ≤ E[t] ≤ Emax_available[t],  and  E[T+1] within terminal policy
```

- `available[t]` is 0 or 1 for a forced/planned outage, 1 otherwise. For a simple first run, use 1 and clearly state no outages modeled.
- `P_charge_max[t]` and `P_dis_max[t]` may differ; nameplate **MW** and energy **MWh** are separate. For the simple version treat them constant and no temperature/SOH derating.
- `Emax_available[t]` can decline with **SOH (state of health)** over longer horizons; for one-day dispatch take it constant if stated.
- The binary mode `u[t]` enforces mutual exclusivity, particularly important when spot prices can be negative.
- Enforce grid interconnection (PCC) limits too; a battery rated at 10 MW does not necessarily have a 10 MW import and export connection:
  
```text
q_PCC[t] = dis[t] - ch[t] - P_aux_AC[t]
-P_grid_import_max ≤ q_PCC[t] ≤ P_grid_export_max
```

- `P_aux_AC[t]` includes AC-site consumption (cooling, BMS, HVAC and other auxiliary loads) **only if charged at the same modeled market meter**. Its treatment differs for behind-the-meter sites or separate auxiliary supply contracts. If auxiliary losses are **DC-side**, instead subtract the appropriate DC energy from `E[t+1]` and **do not subtract them again at the meter**.

### C. Objective: arbitrage, O&M, and wear (essential distinction)

For v1, use **separate accounting** of (i) energy arbitrage, (ii) *variable* operations & maintenance, (iii) incremental cycle degradation, (iv) auxiliary imports and possible tariffs/fees. A transparent example **conditional on all energy settling at the same spot price**:

```text
Profit_variable(s)
  = Σ_t Δt * [
       price[s,t] * (dis[t]-ch[t]-P_aux_AC[t])
       - c_vom_ch * ch[t]
       - c_vom_dis * dis[t]
       - c_deg_dis * dis[t]
       - fees_import[t] * max(ch[t]+P_aux_AC[t]-dis[t],0)
    ]
```

This example is **not immediately an MILP as written** if `max(·,0)` is implemented naïvely; model a **nonnegative import variable** `import_MW[t]` and enforce its relation to net power, with appropriate energy-settlement rules and import/export exclusivity if needed. For the v1 minimal MILP, set `fees_import=0` until site-specific tariffs are documented; retain linear variable O&M and incremental degradation in the existing `c_c,c_d` factors **without counting the same cost twice**.

- `c_vom_ch,c_vom_dis` (EUR/MWh of AC charging/discharging energy) are **both explicitly set to zero for the first experiment on the user's instruction**. Keep them in the profit function as configurable parameters, and flag zero as **ASSUMED, not verified**. Likewise `FOM_daily=0 EUR/day` is a deliberate first-run accounting assumption. No site contract or project-specific public number was inferred.
- `c_deg_dis` (EUR/MWh AC discharged) is a **simple linear wear proxy** calibrated from replacement economics/warranty throughput, **not** an exact physical aging model. More advanced lifecycle models consider depth of discharge, SOC level, calendar aging, temperature, and the manufacturer's throughput/cycle warranty.
- **Fixed O&M** `FOM` (often EUR/MW/year or fraction of CAPEX per year) is a **constant for an already installed asset** over a single 24-hour dispatch. Therefore `-FOM_daily` changes **reported net financial profit** but **not the profit-maximizing schedule**. In the approved initial experiment, `FOM_daily=0 EUR/day` but the line remains visible in accounting. If comparing operating strategies, report gross margin, variable net margin, and allocated FOM separately.
- Likewise **CAPEX and financing** affect investment feasibility/LCOS, not short-horizon marginal dispatch if they are sunk and invariant. **Do not mislabel a throughput depreciation charge as the ATB's fixed O&M**.
- **Auxiliary consumption** can materially affect margins and net power; if simplified away, disclose `P_aux=0` rather than implying a fully modeled industrial site.

### D. Cycles, warranty, and lifetime

- A transparent energy-throughput proxy for **equivalent full cycles** (EFC) on usable-capacity basis is
  `EFC ≈ [Σ_t (dis[t]/ηd)*Δt] / (Emax - Emin)`. Here the numerator is internal stored energy withdrawn; the denominator is the usable internal energy span. The definition **depends on the warranty/meter convention**; do not silently equate this to rainflow depth-dependent cycle counting.
- For a warranty/operations cap, optionally impose `EFC_day ≤ EFC_limit` (or a yearly throughput budget in a longer horizon). Enforce both a degradation *cost* and *limit* only when they reflect distinct economic wear and contractual compliance, not duplicated penalties.
- Higher-fidelity physics can add `SOH[t]`, cycle/calendar degradation, temperature-dependent available capacity and charge-rate derating (typically requiring calibration and potentially nonlinear/piecewise linear models). NREL SAM treats cycle- and calendar-aging as separate causes of capacity loss.

### E. Operational checks and actual-market caveats

- Validate feasibility, energy conservation, prices including negative values, SOC units, charge/discharge interlock, terminal energy, and rolling day-to-day continuity.
- Battery management system / manufacturer restrictions can further impose temperature, voltage/current, allowable C-rate, reserve margin, and outage restrictions. Grid connection and power-conversion system ratings can be stricter than battery ratings.
- **Day-ahead market modeling caveat:** a fixed signed schedule optimized using a single ex-ante price forecast is an **educational price-taker benchmark**, not a complete description of bidding/clearing in a coupled day-ahead auction. An actually executable industrial bidding model needs bid curves, acceptance uncertainty, delivery obligations, imbalance/settlement rules, and compliance with the specific auction's products.
- Scenario-specific post-clearance physical schedules **without a genuine recourse mechanism and nonanticipativity** create artificial perfect foresight.
- All three strategies must use identical physical feasible sets and cost accounting; only forecast info/objectives change.

### Recommended scope decision

**Implement in the first small, reviewable codebase**: AC terminal power definitions, charge/discharge MW limits, SOC min/max, initial/terminal SOE, separate ηc/ηd, binary mutual exclusivity, grid import/export limits (even if equal to PCS limits), variable O&M, a justified simple degradation €/MWh discharge proxy, and a report of fixed O&M outside the dispatch objective. Optional AC auxiliary load can be one constant parameter and priced correctly if the settlement meter assumption holds.

**Defer explicitly**: thermal electrochemistry, nonlinear SOH evolution, rainflow-counted aging, detailed component outages, price-dependent auction bids and execution, intraday/balancing-market co-optimization, site-specific grid/tax charges and advanced degradation; add only with sourced site parameters.

**Missing project input—not invented:** PCS MW charge/discharge power, BESS nominal/usable MWh, SOC window and initial/final values, round-trip or separate efficiencies, FOM and VOM basis, degradation/warranty inputs, grid connection import/export MW, auxiliary load and site metering arrangement. Examples from reference models are **not manufacturer's specifications**.

### Source references for this industry-practice audit

1. NREL System Advisor Model, *Front-of-Meter Battery Dispatch*: charge/discharge priority, SOC bounds, grid charging and conversion losses: https://samrepo.nlr.gov/help/battery_dispatch_fom.html
2. NREL System Advisor Model, *Battery Life*: cycle and calendar degradation, DOD, temperature and replacement: https://samrepo.nlr.gov/help/battery_life.html
3. NREL SAM, *Battery System Losses*: AC/DC ancillary consumption, mode-dependent loads: https://samrepo.nlr.gov/help/battery_storage_btm.html
4. NREL/NLR, *2025 Annual Technology Baseline — Utility-Scale Battery Storage*: fixed O&M accounting, BESS cost/performance reference values, representative round-trip efficiency (not site-specific): https://atb.nlr.gov/electricity/2025/utility-scale_battery_storage
5. NREL, published battery dispatch optimization formulation with operating charge/discharge costs, rated power, SOC and cycle count: https://docs.nrel.gov/docs/fy22osti/82726.pdf
6. NREL SAM, overall battery dispatch and engineering model scope: https://sam.nrel.gov/battery-storage/


## Evaluation

- Day-by-day walk-forward / held-out comparison of **realized EUR profit**, risk (bad-day tail losses, CVaR), charge/discharge and SOC trajectories, throughput, and total degradation.
- Quantile forecast calibration (pinball loss and actual coverage), and scenario-path diagnostics: spikes, negative prices, intraday day spread, residual autocorrelation and daily dynamics.
- Plot distributions and daily realized profit with `matplotlib`, manipulate data with `pandas`/`numpy`, train forecasts with `scikit-learn`.
- Do not call the perfect-foresight result actual achievable economic profit. It is an **oracle upper bound for a fixed, simplified dispatch formulation**.
- Do not promise stochastic outperforming deterministic: differences depend on calibration, uncertainty, risk aversion, and realized price paths.

## Proposed small project layout (not yet implemented)

- `data.py`: API fetching / source validation / datetime and DST.
- `scenarios.py`: `scikit-learn` conditional quantile forecast and daily-vector residual bootstrap.
- `battery.py`: common physical BESS model and three objective definitions.
- `compare.py`: chronological out-of-sample experiment, summary metrics, matplotlib plots.
- `requirements.txt`: `numpy`, `pandas`, `matplotlib`, `scikit-learn`, HTTP client, and selected optimizer dependency.
- `README.md`: how to reproduce data, train, run and inspect outputs.

**Next technical dependencies:** Verify public market-price retrieval and choose illustrative BESS specs, risk coefficient, optimizer and archived features before claiming an executable result.

## Sources

1. European Commission (2025-10-01), 15-minute EU day-ahead market time unit: https://energy.ec.europa.eu/news/eu-electricity-trading-day-ahead-markets-becomes-more-dynamic-2025-10-01_en
2. Fraunhofer ISE Energy-Charts API: https://api.energy-charts.info/
3. scikit-learn quantile boosting: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
4. Hilger et al., *Multivariate scenario generation of day-ahead electricity prices using normalizing flows*, Applied Energy 367 (2024), 123241. Provides a benchmark using informed historical nearest neighbours, not validation for this exact residual-bootstrap combination: https://doi.org/10.1016/j.apenergy.2024.123241
