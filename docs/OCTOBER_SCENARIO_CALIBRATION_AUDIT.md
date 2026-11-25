# October 2026 scenario calibration audit

**Status:** Diagnostic, development-period evaluation; not an untouched holdout.

**Source:** GitHub Actions run
artifact `monthly-battery-evaluation` (ID `13590239085`), commit
`a2e9cf617aba036d23417666562a5ae544a79202`.
The artifact includes `monthly_2026-10.json`.

## Measured results

| Diagnostic | October 2026 |
| --- | ---: |
| Eligible delivery days | 30 |
| Nominal scenario 10th–90th percentile band coverage | 80.0% |
| Empirical 10th–90th percentile band coverage | **61.81%** |
| Observed prices above scenario 90th percentile | **32.88%** |
| Observed prices below scenario 10th percentile | **5.31%** |
| Mean absolute error of scenario median | **€62.92/MWh** |

These metrics are pooled over eligible 15-minute intervals. They are
descriptive diagnostics, not statistically independent observations.
The October 25 daylight-saving day (100 intervals) is excluded.

## Chronological deterioration within October

Splitting the 30 eligible days into the first and last 15 days
(October 25 is excluded) reveals a substantial temporal change:

| Eligible-day segment | Above scenario 90th percentile | 10th–90th band coverage |
| --- | ---: | ---: |
| First 15 days | 23.06% | 73.54% |
| Last 15 days | 42.71% | 50.07% |

The most severe upper-tail misses are concentrated near month-end:
October 28 (97.92% of intervals above the 90th percentile),
October 29 (94.79%), October 30 (86.46%), and October 31 (100%).
These figures come directly from the artifact's per-day diagnostic rows.

This split was chosen *after inspecting October* and is exploratory.
It is not a prospective change-point test, and the cause is unknown.
It motivates checking temporal model drift, median forecast bias,
and upper-tail residuals on earlier chronological validation periods.

## Interpretation

The model's October scenario ensemble is **underdispersed and strongly
biased toward missing high-price outcomes**. A nominal 80% interval
covers only about 62% of observed prices, and high-side misses are much
more frequent than low-side misses. A favorable realized battery profit
does not compensate for poor scenario calibration when interpreting
CVaR-based risk claims.

The scenario 10th/90th percentiles are *empirical quantiles of 50
generated paths*. They are not automatically calibrated predictive
quantiles. The diagnostic does not establish the cause of the error:
possible contributors include shifted market conditions, conditional
model bias, insufficient residual diversity, and the additive
calibration-gap procedure.

## Research guardrails and next steps

1. **Do not tune using October and then call October an untouched
   out-of-sample test.** It is already a development-period month.
2. Investigate the upper-tail error using *earlier* chronological
   validation windows and only historical inputs available before each
   delivery month. Keep the candidate method and tuning decisions
   explicit.
3. Examine daily and hourly coverage, median bias, scenario spread,
   and extreme-price errors. Consider methods that address asymmetric
   upper-tail misses, but validate any changes prospectively.
4. Retain the current October result as a versioned baseline and
   record any subsequent model revisions separately.
5. Evaluate November only after its complete validated price history
   is available. October may serve as calibration/selection, but
   November must remain unseen during model adjustment for a valid
   prospective comparison.

**Conclusion:** The pipeline executes successfully, but October's
scenario ensemble fails a basic descriptive calibration check. Claims
of reliable price-tail or CVaR calibration are not supported.
