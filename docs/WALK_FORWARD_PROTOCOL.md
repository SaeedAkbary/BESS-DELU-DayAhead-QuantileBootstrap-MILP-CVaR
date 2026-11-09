# Multi-month BESS walk-forward evaluation protocol

## Scope and status

The reproducible multi-month evaluation pipeline is implemented on
`feature/battery-optimization-foundation`, but **multi-month empirical
results are not yet available**. The validated reference price artifact
covers October 2025 through October 2026. November 2026 is not a
completed delivery month as of 2026-11-07.

The October-only diagnostic is recorded in
[`ROLLING_OCTOBER_RESULTS.md`](ROLLING_OCTOBER_RESULTS.md). October has
been used during model development, so it is **not an untouched holdout**.

## Evaluation procedure

1. Obtain a complete, validated 15-minute DE-LU historical price series.
   Reject missing prices, duplicate timestamps, irregular UTC spacing,
   truncated files, and requests for incomplete calendar months.
2. For each target month from October 2026 onward, fit quantile
   regression on dates strictly before the target month.
3. Calibrate the additive interval gap using the preceding calendar
   month and a separate model fit strictly before that calibration month.
4. Reuse February–August 2026 out-of-sample daily residual templates.
   This fixed residual library is a development choice, not a fully
   adaptive residual calibration method.
5. Generate the same 50 daily price scenarios for all five candidate
   risk weights (lambda 0, 0.25, 0.5, 1, 2). Evaluate realized
   profits using observed prices only after dispatch decisions.
6. Use the first available evaluation month for risk-weight selection
   only. For each later month, select lambda using maximum total
   realized profit in strictly preceding evaluated months. Ties
   favor the smaller lambda. Report risk-neutral and perfect-foresight
   oracle comparisons.
7. Preserve month-specific selection cutoffs, selection months, and
   sample counts in the JSON report.

The pipeline skips non-96-interval days, including autumn and spring
daylight-saving transitions. Excluded dates must be reported, and
annualized financial claims should account for the exclusions.

## Execution

After the last day of November 2026, open the GitHub Actions workflow
[`Multi-month walk-forward battery backtest`](../.github/workflows/battery_walk_forward.yml)
and run it with `through_month=2026-11`. The workflow downloads the
original validated history artifact, fetches and validates complete
new months, executes the sequential monthly evaluations, and uploads
the extended prices and JSON reports.

For local execution with validated prices:

```bash
python run_battery_walk_forward.py \
  --history output/extended_prices.csv \
  --first-month 2026-10 \
  --last-month 2026-11 \
  --output-dir output/rolling
```

The command refuses incomplete months. The workflow is manually
triggered and **has not yet been verified end to end for two months**.

## Statistical interpretation

The report includes:
- Total and average daily realized profit for selected, risk-neutral,
  and oracle policies.
- Empirical CVaR of daily losses at alpha=0.95. With few delivery days,
  the worst tail contains very few observations.
- A paired iid-day bootstrap interval for the **mean daily**
  selected-minus-risk-neutral profit difference. It assumes independent
  days and can understate uncertainty under serial correlation.
- A paired month-block bootstrap interval, resampling entire months.
  It is suppressed until at least three evaluated months exist.
  Even three blocks provide fragile inference.

Neither bootstrap interval should be presented as proof of superior
out-of-sample performance. The selection rule itself maximizes
historical realized profit, rather than a prespecified risk-return
utility. A genuine prospective validation requires future months
unseen during design and tuning.

## Physical and economic assumptions

The battery is illustrative (2 MWh capacity, 1 MW power, 95% charge
and discharge efficiency, 1 MWh initial/terminal energy, zero variable
Daily terminal SOC equals initial SOC; interday energy carryover,
degradation, market fees, imbalance risk, availability, and network
constraints are not fully modeled. Perfect foresight is an unattainable
oracle upper bound, not an implementable trading strategy.

## Acceptance criteria for future results

- All CI tests pass at the evaluated commit.
- Every target month is complete and sourced from validated prices.
- Every month's scenario model and calibration use strictly earlier
  dates, and all risk weights share the same generated scenarios.
- Every lambda selection uses only prior evaluated months.
- Skipped days, calibration metadata, model parameters, and artifact
  provenance are preserved.
- Profit and risk statistics are reported alongside uncertainty
  limitations, not as guaranteed economic returns.
