"""Standalone HTML report and plots derived only from executed JSON outputs."""
from html import escape
from pathlib import Path
import json
import numpy as np


def render_report(bundle, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    base = bundle["experiments"][0]
    daily = base["comparison_daily"]
    strategies = ("zero_dispatch", "risk_neutral", "risk_aware", "oracle")
    dates = [r["day"] for r in daily]
    labels = {"zero_dispatch": "Zero dispatch", "risk_neutral": "Risk-neutral MILP",
              "risk_aware": base["risk_aware_label"], "oracle": "Perfect foresight (unattainable)"}
    files = []
    for mode, title in (("daily", "Daily simulated net P&L (EUR)"),
                        ("cumulative", "Cumulative simulated net P&L (EUR)"),
                        ("drawdown", "Net-P&L drawdown from running peak (EUR)")):
        fig, ax = plt.subplots(figsize=(10, 4), layout="constrained")
        for strategy in strategies:
            values = np.array([r[strategy] for r in daily])
            if mode != "daily":
                cumulative = np.r_[0, values.cumsum()]
                values = cumulative[1:] if mode == "cumulative" else (np.maximum.accumulate(cumulative) - cumulative)[1:]
            ax.plot(range(len(dates)), values, label=labels[strategy], linewidth=1.3)
        ticks = np.unique(np.linspace(0, len(dates) - 1, min(6, len(dates)), dtype=int))
        ax.set_xticks(ticks, [dates[i] for i in ticks], rotation=15)
        ax.set(title=title, xlabel="Eligible Berlin delivery date; excluded days omitted", ylabel="EUR")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
        name = f"{mode}.svg"
        fig.savefig(destination / name)
        fig.savefig(destination / f"{mode}.png", dpi=130)
        plt.close(fig)
        files.append(name)
    cases = bundle["experiments"]
    if len(cases) > 1:
        fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
        ax.barh([c["name"] for c in cases], [c["comparison"]["risk_neutral"]["net_profit_eur"] for c in cases])
        ax.set(xlabel="Re-optimized risk-neutral simulated net P&L (EUR)",
               title="Illustrative sensitivity; OAT and joint stresses identified in table")
        fig.savefig(destination / "sensitivity.svg")
        fig.savefig(destination / "sensitivity.png", dpi=130)
        plt.close(fig)
        files.append("sensitivity.svg")

    def table(rows, fields):
        def value(v):
            return f"{v:,.3f}" if isinstance(v, float) else str(v)
        return ("<table><thead><tr>" + "".join(f"<th>{escape(label)}</th>" for _, label in fields)
                + "</tr></thead><tbody>" + "".join("<tr>" + "".join(
                    f"<td>{escape(value(row.get(key, 'pending')))}</td>" for key, _ in fields)
                    + "</tr>" for row in rows) + "</tbody></table>")

    rows = [{"strategy": labels[k], **base["comparison"][k]} for k in strategies]
    reconciliation = table(rows, [("strategy", "Strategy"), ("gross_arbitrage_profit_eur", "Gross EUR"),
        ("transaction_costs_eur", "Trading fees EUR"), ("degradation_costs_eur", "Degradation EUR"),
        ("other_variable_costs_eur", "Other variable EUR"), ("net_profit_eur", "Net EUR")])
    risk = table(rows, [("strategy", "Strategy"), ("days", "Days"),
        ("mean_daily_profit_eur", "Mean EUR/day"), ("median_daily_profit_eur", "Median EUR/day"),
        ("std_daily_profit_eur", "Std EUR/day"), ("worst_daily_net_loss_eur", "Worst loss EUR"),
        ("negative_profit_days_pct", "Negative days %"), ("maximum_drawdown_eur", "Max drawdown EUR"),
        ("empirical_var_loss_eur", "Loss VaR EUR"), ("empirical_cvar_loss_eur", "Loss CVaR EUR"),
        ("charge_throughput_mwh", "Charge MWh"), ("discharge_throughput_mwh", "Discharge MWh"),
        ("net_profit_per_mwh_discharged", "Net EUR/MWh discharged")])
    sensitivity = table([{"name": c["name"], "kind": c["kind"],
        "neutral": c["comparison"]["risk_neutral"]["net_profit_eur"],
        "aware": c["comparison"]["risk_aware"]["net_profit_eur"],
        "cvar": c["comparison"]["risk_aware"]["empirical_cvar_loss_eur"],
        "selection": "evaluated" if c["walk_forward"] else "pending: one month",
        "zero_days": c["risk_neutral_zero_dispatch_days"],
        "negative": c["comparison"]["risk_neutral"]["negative_profit_days"]} for c in cases],
        [("name", "Experiment"), ("kind", "Design"), ("neutral", "Neutral net EUR"),
         ("aware", "Aware net EUR"), ("cvar", "Aware CVaR EUR"),
         ("zero_days", "Neutral idle days"), ("negative", "Neutral negative days"),
         ("selection", "Prior-month selector")])
    diagnostics = [{"month": m["month"], "training_before": m["model_training_before"],
        "calibration": m["calibration_month"], "days": len(m["daily"]),
        "skipped": str(m["skipped_days"]),
        "coverage": m["scenario_diagnostics"]["observed_band_coverage"]} for m in base["monthly"]]
    diag = table(diagnostics, [("month", "Month"), ("training_before", "Training before"),
        ("calibration", "Calibration month"), ("days", "Eligible days"),
        ("skipped", "Exclusions"), ("coverage", "Scenario 10–90 coverage")])
    regime_rows = [{"month": m["month"], "regime": regime, "policy": w, **values}
        for m in base["monthly"] for regime, policies in m.get("realized_volatility_regime_summary", {}).items()
        for w, values in policies.items() if w in ("0.0", "1.0")]
    regime_table = table(regime_rows, [("month", "Month"), ("regime", "Realized volatility stratum"),
        ("policy", "Fixed lambda"), ("days", "Days"), ("net_profit_eur", "Net EUR"),
        ("empirical_cvar_loss_eur", "Loss CVaR EUR")])
    protocol = ("Walk-forward selection executed using only prior months."
                if base["walk_forward"] else "Walk-forward selection pending: fewer than two complete evaluation months. Risk-aware display uses prespecified lambda=1; it is not selected from this month's results.")
    images = "".join(f'<figure><img src="{name}" alt="{name}"></figure>' for name in files)
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>BESS commercial backtest</title>
<style>body{{font:15px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;color:#182536}}table{{border-collapse:collapse;display:block;overflow:auto}}td,th{{padding:9px;border:1px solid #ccd4dd;text-align:right}}th{{background:#edf2f7}}pre{{white-space:pre-wrap}}img{{max-width:100%}}</style>
<h1>BESS commercial historical simulation</h1>
<h2>Executive summary</h2><p>Executed research simulation for {escape(dates[0])} through {escape(dates[-1])}. October 2026 is development data. No live trading revenues or untouched October holdout are claimed. {protocol}</p>
<h2>Market and battery assumptions</h2><p>DE-LU 15-minute prices; grid-side MW/MWh; daily cyclic SOC. Costs and battery parameters are illustrative, not verified tariffs or asset specifications.</p><pre>{escape(json.dumps(base['config'], indent=2))}</pre>
<h2>Source provenance and evaluation dates</h2><pre>{escape(json.dumps(bundle['provenance'], indent=2))}</pre>
<h2>Gross-to-net reconciliation</h2>{reconciliation}
<p>Net = sales minus purchases minus trading fees minus discharge degradation minus execution and legacy O&amp;M. Signed purchases preserve negative-price credits.</p>
<h2>Risk-neutral versus risk-aware performance</h2>{risk}
<p>Loss = negative daily net P&amp;L. Empirical VaR uses the inverse ECDF and CVaR the exact fractional upper tail. These are historical daily metrics, not optimization-time scenario CVaR. Negative loss CVaR is valid. The oracle is unattainable.</p>
<h2>Daily P&amp;L, cumulative P&amp;L and drawdown</h2>{images}
<h2>Cost, degradation and robustness experiments</h2>{sensitivity}
<p>All dispatches are re-optimized. Uncertainty scaling changes generated paths around their forecast mean, not observed market prices; it is an illustrative forecast-uncertainty stress, not evidence from a different historical regime. Negative realized days mean idle would have been better in hindsight, not that this was known at dispatch.</p>
<h3>Observed volatility strata</h3>{regime_table}<p>Ex-post daily price standard deviation is compared with training-only 25th/75th percentile thresholds. Strata do not drive dispatch. Empty strata are omitted; small samples cannot establish regime robustness.</p>
<h2>Walk-forward diagnostics</h2><p>{protocol}</p>{diag}
<h2>Statistical uncertainty and sample limitations</h2><pre>{escape(json.dumps(base['uncertainty'], indent=2))}</pre>
<p>The paired iid-day bootstrap ignores serial dependence. Month-block inference is withheld with fewer than three evaluated months. Tail estimates based on a few days are unstable; no economic superiority is established.</p>
<h2>Commercial interpretation and remaining limitations</h2><p>Operating net arbitrage P&amp;L excludes capex, fixed O&amp;M, financing, taxes, imbalance, availability, network constraints and market impact. Linear discharge degradation does not model calendar aging, cycle depth or nonlinear state of health. Publication vintages are unverified, so chronological training does not establish pre-auction tradability. DST days with 92/100 intervals remain unsupported. November 2026 is incomplete as of 2026-11-23 and is not a completed result.</p>
<p>Full reproducible parameters, schedules, accounting and selection diagnostics: <a href="results.json">results.json</a>.</p></html>"""
    (destination / "report.html").write_text(body, encoding="utf-8")


def write_pending_report(destination):
    path = Path(destination)
    path.mkdir(parents=True, exist_ok=True)
    sections = ["Executive summary", "Market and battery assumptions", "Gross-to-net reconciliation",
                "Risk-neutral versus risk-aware performance", "Daily and cumulative net P&L",
                "Drawdown", "Cost and degradation sensitivity", "Walk-forward diagnostics",
                "Statistical uncertainty and sample size", "Commercial limitations"]
    (path / "report.html").write_text('<html lang="en"><meta charset="utf-8"><h1>Pending commercial backtest</h1>'
        + ''.join(f"<h2>{escape(s)}</h2><p>Pending validated history and executed model outputs.</p>" for s in sections)
        + '<p>No results or charts fabricated. October 2026 is development data; November 2026 is incomplete as of 2026-11-23.</p></html>', encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True)
    args = parser.parse_args()
    source = Path(args.results)
    render_report(json.loads(source.read_text(encoding="utf-8")), source.parent)
