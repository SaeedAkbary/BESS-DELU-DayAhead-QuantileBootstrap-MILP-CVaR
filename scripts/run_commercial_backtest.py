"""Re-optimize commercial sensitivities using the existing monthly framework."""
import argparse
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path
import subprocess
from datetime import datetime, timezone

from battery_optimization import Battery
from scenarios import prepare
from battery_monthly_scenarios import build_month, evaluate_inputs
from battery_walk_forward import evaluate_months
from scripts.run_battery_walk_forward import validate_completed_months
from src.battery_config import load_config, experiment_configs
from src.battery_metrics import summarize_net
from src.battery_uncertainty import paired_profit_bootstrap, month_block_profit_bootstrap
from src.battery_commercial_report import render_report, write_pending_report


def compare_reports(reports, config):
    walk = None
    if len(reports) >= 2:
        walk = evaluate_months(reports, selection_rule=config["selection_rule"],
            downside_penalty=config["downside_penalty"], lookback_months=config["lookback_months"])
        daily = []
        for month in walk["monthly"]:
            for row in month["daily"]:
                daily.append({"day": row["day"], "risk_aware": row["selected"],
                    "risk_neutral": row["risk_neutral"], "oracle": row["oracle"], "zero_dispatch": 0.,
                    "accounting": {("risk_aware" if k == "selected" else k): v for k, v in row["accounting"].items()}})
        label = "Prior-month-selected CVaR MILP"
    else:
        daily = [{"day": r["day"], "risk_aware": r["1.0"], "risk_neutral": r["0.0"],
            "oracle": r["oracle"], "zero_dispatch": 0., "accounting": {k: r["accounting"][w] for k, w in
             (("risk_aware", "1.0"), ("risk_neutral", "0.0"), ("oracle", "oracle"), ("zero_dispatch", "zero_dispatch"))}}
             for r in reports[0]["daily"]]
        label = "CVaR MILP (prespecified lambda=1)"
    summary = {k: summarize_net([r[k] for r in daily], config["alpha"],
                [r["accounting"][k] for r in daily])
               for k in ("risk_aware", "risk_neutral", "oracle", "zero_dispatch")}
    pairs = [{"day": r["day"], "selected": r["risk_aware"], "risk_neutral": r["risk_neutral"]} for r in daily]
    return dict(walk_forward=walk, comparison=summary, comparison_daily=daily,
        risk_aware_label=label, risk_neutral_zero_dispatch_days=sum(
            r["accounting"]["risk_neutral"]["charge_throughput_mwh"] +
            r["accounting"]["risk_neutral"]["discharge_throughput_mwh"] < 1e-7 for r in daily),
        uncertainty={"paired_days": paired_profit_bootstrap(pairs, seed=config["seed"]),
                     "month_blocks": month_block_profit_bootstrap(pairs, seed=config["seed"])})


def run_experiments(history, months, config, *, progress=print):
    # Validate the entire configuration before performing any expensive solves.
    cases = list(experiment_configs(config))
    table = prepare(history)
    cache, results = {}, []
    for name, kind, settings in cases:
        monthly = []
        for month in months:
            key = (month, settings["scenario_count"], settings["seed"])
            if key not in cache:
                cache[key] = build_month(table, month, scenario_count=settings["scenario_count"], seed=settings["seed"])
            inputs, metadata = cache[key]
            scale = settings["volatility_scale"]
            transformed = [(day, paths if scale == 1 else paths.mean(axis=0) + scale * (paths - paths.mean(axis=0)), actual)
                           for day, paths, actual in inputs]
            report = evaluate_inputs(transformed, {**metadata, "volatility_scale": scale},
                                     Battery(**settings["battery"]), alpha=settings["alpha"])
            monthly.append(report)
            progress(f"{name} / {month}: re-optimized {len(report['daily'])} days", flush=True)
        results.append({"name": name, "kind": kind, "config": settings, "monthly": monthly,
                        **compare_reports(monthly, settings)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history")
    parser.add_argument("--first-month", default="2026-10")
    parser.add_argument("--last-month", default="2026-10")
    parser.add_argument("--config", default="config/commercial.example.json")
    parser.add_argument("--output-dir", default="output/commercial")
    parser.add_argument("--pending", action="store_true", help="Write an explicitly pending report without results")
    args = parser.parse_args()
    output = Path(args.output_dir)
    if args.pending:
        write_pending_report(output)
        return
    if not args.history:
        parser.error("--history is required unless --pending")
    if (output / "results.json").exists():
        raise ValueError("Output already contains results; choose a new directory to preserve experiments")
    months = validate_completed_months(args.first_month, args.last_month)
    config = load_config(args.config)
    results = run_experiments(args.history, months, config)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    provenance = {"history_file": Path(args.history).name,
        "history_sha256": hashlib.sha256(Path(args.history).read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(Path(args.config).read_bytes()).hexdigest(),
        "source": config.get("source_provenance", "User-supplied history; source attribution must be verified"),
        "executed_at_utc": datetime.now(timezone.utc).isoformat(), "git_head": commit,
        "git_dirty": bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()),
        "python": platform.python_version(),
        "dependencies": {k: version(k) for k in ("numpy", "pandas", "pyomo", "highspy", "scikit-learn")},
        "months": months, "publication_vintages_verified": False}
    bundle = {"provenance": provenance, "experiments": results}
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(bundle, indent=2, allow_nan=False), encoding="utf-8")
    render_report(bundle, output)
    print(f"Report: {output / 'report.html'}")


if __name__ == "__main__":
    main()
