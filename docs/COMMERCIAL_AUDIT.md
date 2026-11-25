# Pre-implementation audit

Baseline: f00d795. Read the root compatibility shims, src modules, scripts,
tests, research notes and workflow configuration before implementation.

- Pyomo/HiGHS already enforce fixed common dispatch, binary operating mode,
  efficiencies, interval duration, energy bounds and fixed terminal SOC.
- The sole cost is variable_cost_eur_mwh on grid-side charge plus discharge.
  Historical scoring duplicates that expression; dedicated trading fees,
  discharge degradation and component reconciliation are absent.
- Monthly forecasts train before the target month; calibration models train
  before the previous month. Residual folds are anchored before September 2026.
  Prior-day features do not use target-day prices, but archived publication
  vintages are unavailable: chronological separation alone is not tradability.
- The multi-month CLI rejects uncompleted months, but direct monthly and report
  APIs lack full completeness enforcement. prepare does not reject infinity,
  missing intervals or missing calendar days. Report rows need sorting before
  cumulative metrics. DST days are excluded and must remain explicit.
- Historical selection maximizes earlier profit. A frozen economic downside
  penalty and reproducible sensitivity configuration are missing.
- Existing reports include daily profit, scenario diagnostics and bootstrap
  uncertainty. They lack component accounting, drawdown, throughput and a
  commercial report. Existing empirical CVaR uses a threshold-tail mean;
  preserve it for original research reproduction and name the new exact-tail
  convention separately.
- Preserve root imports/CLIs, zero-cost defaults, original October documents
  and figures, and all existing Actions workflows. No raw history is tracked.

Baseline executed in isolated WSL Python 3.14.4 with requirements.txt:
68 tests; three failures in the CLI-help equality test (Python 3.14 gives
module invocations a different default program name). All other tests passed.
The initial Windows Python alias could not execute; the first WSL attempt
lacked dependencies. These environment failures are not passing test runs.
