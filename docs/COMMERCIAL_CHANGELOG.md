# Technical change log

- Added backward-compatible Battery cost fields and shared optimization/scoring
  accounting; reject negative/nonfinite economic parameters and ambiguous legacy
  scoring arguments. Preserve all-zero-cost defaults and existing physical MILP.
- Solver results are loaded only after optimality is established; missing solver
  and infeasible models fail explicitly. Scenario CVaR is labeled separately.
- Added commercial empirical risk, gross-to-net, throughput and drawdown metrics.
  Historical October threshold-tail metrics remain available for reproduction.
- Strengthened source and calendar validation, direct monthly completeness,
  report chronology, exclusion accounting and source-vintage limitations.
- Added prior-month net/downside selection alongside historical profit selection.
- Added strict experiment configuration, shared-scenario re-optimization,
  efficiency/count/uncertainty stresses and ex-post volatility strata.
- Added a reproducible commercial CLI, provenance, HTML/SVG reporting, pending
  report mode and isolated output directories. Existing root CLIs still work.
- Fixed Python 3.14 CLI-help compatibility by explicitly setting program names.
- Extended automated tests and existing CI branch coverage; added matplotlib
  only for static reporting. Original research documents and figures unchanged.

Validation and executed historical findings are recorded separately in
COMMERCIAL_RESULTS.md. No multi-month untouched result is claimed.
