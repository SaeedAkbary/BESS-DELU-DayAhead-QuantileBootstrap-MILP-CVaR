# Single-month BESS demonstration (October 2026)

This is a research/portfolio demonstration, not a verified commercial trading system. October 2026 was used during development and is **not** a pristine out-of-sample holdout.

## Prerequisites

Install Python dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
```

Provide a **validated, complete** 15-minute DE-LU historical electricity-price CSV, covering sufficient prior training history and October 2026. It must be compatible with `scenarios.prepare`; do not use an incomplete or unverified price file. The battery model requires Pyomo and HiGHS.

## Run the full single-month pipeline

```bash
python battery_monthly_scenarios.py \
  --history output/extended_prices.csv \
  --month 2026-10 \
  --output output/october_demo.json \
  --seed 42
```

Replace `output/extended_prices.csv` with the actual location of your validated history file. The command generates price scenarios, solves battery dispatches for each candidate CVaR risk weight, evaluates realized profit, and writes a JSON report.

## Read the output

The report includes `summary` (risk-weight results), `oracle` (unattainable perfect-foresight comparison), `scenario_diagnostics`, `skipped_days`, and `daily`. For each eligible day, `daily[i].dispatch[weight]` contains `charge_mw` and `discharge_mw` (96 quarter-hour intervals each) and `energy_mwh` (97 state-of-charge points, including initial and terminal states). For example, `daily[0].dispatch["1.0"]` is the risk-weight-1 schedule. `daily[i][weight]` remains realized profit in EUR. The oracle schedule is **not** an executable trading strategy.

The illustrative battery has 2 MWh energy capacity, 1 MW power, 95% charging/discharging efficiency, and 1 MWh initial/terminal energy. These parameters are not verified site specifications. The model does not fully account for degradation, fees, imbalance costs, or network constraints.

## Tests

```bash
python -m unittest test_battery_monthly_scenarios.py
```

This test checks monthly boundaries, temporal isolation, and dispatch-report structure using mocked scenarios/solves. It is **not** a full live-history end-to-end integration test. Full integration verification with the validated history and solver remains a separate acceptance step.
