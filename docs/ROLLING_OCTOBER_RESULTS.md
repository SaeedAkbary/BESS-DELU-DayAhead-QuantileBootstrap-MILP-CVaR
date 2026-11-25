# Rolling monthly evaluation: October 2026 diagnostic

This report records the first successful end-to-end execution of
`battery_monthly_scenarios.py`. It is **not** a multi-month walk-forward
validation and must not be treated as independent model selection evidence.

- Artifact: `monthly-battery-evaluation` / `monthly_2026-10.json`
- Source: validated DE-LU historical price artifact from run 42305243042
- Evaluated days: 30; 2026-10-25 (100 intervals, DST) excluded
- Calibration month: September 2026; 50 daily scenarios
- Model training cutoff: 2026-10-01 (exclusive)
- Calibration-model training cutoff: 2026-09-01 (exclusive)
- Historical residual folds: before 2026-09-01
- Calibration gap: 46.9094 EUR/MWh
- Battery: 2 MWh, 1 MW, 95% charge/discharge efficiency,
  initial and terminal energy 1 MWh, zero variable O&M
- SOC: daily cyclic, no interday carryover; battery parameters unverified

| Risk weight | Realized total EUR | Empirical CVaR daily loss EUR |
| ---: | ---: | ---: |
| 0.0 | 6308.94 | 20.29 |
| 0.25 | 6204.00 | 12.65 |
| 0.5 | 6238.28 | 13.21 |
| 1.0 | 6368.11 | 9.67 |
| 2.0 | 6371.48 | -1.49 |
| Oracle | 10409.79 | -129.37 |

The highest realized October profit occurs at lambda=2.0, but choosing
lambda on the basis of October outcomes would contaminate an October
holdout. The 95% empirical CVaR estimate is unstable with 30 daily
observations. A negative loss CVaR means even the estimated worst-tail
daily profit is positive, not that losses are impossible.

The frozen earlier October benchmark used a different scenario calibration
method and is not directly comparable as a controlled battery-policy test.
Both October experiments are exploratory.

**Next:** Obtain complete validated history for additional evaluation months,
run the same monthly pipeline, then apply `battery_walk_forward.py`
with strictly prior-month selection. Do not report multi-month results
until at least two eligible monthly JSON reports exist.
