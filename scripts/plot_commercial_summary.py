"""Render graphical summaries from committed executed evidence; no model rerun."""
import argparse
import json
from pathlib import Path
import numpy as np


def plot_summary(summary, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base = summary["experiments"][0]
    names = ("risk_neutral", "risk_aware")
    labels = ("Risk-neutral", "CVaR (fixed lambda=1)")
    colors = ("#2563a6", "#218c74")
    period = ", ".join(summary["provenance"]["months"])
    days = base["comparison"]["risk_neutral"]["days"]
    note = f"{period} | {days} eligible days | Development simulation; illustrative costs"

    def save(fig, name):
        fig.savefig(output / f"{name}.png", dpi=150)
        fig.savefig(output / f"{name}.svg")
        svg = output / f"{name}.svg"
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n", encoding="utf-8")
        plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), layout="constrained")
    for ax, name, label in zip(axes, names, labels):
        row = base["comparison"][name]
        amounts = [row["gross_arbitrage_profit_eur"], -row["transaction_costs_eur"],
                   -row["degradation_costs_eur"], -row["other_variable_costs_eur"], row["net_profit_eur"]]
        running = 0.
        for i, amount in enumerate(amounts):
            bottom = 0. if i in (0, 4) else running + min(amount, 0.)
            height = amount if i in (0, 4) else abs(amount)
            ax.bar(i, height, bottom=bottom, color="#218c74" if i == 4 else "#2563a6" if i == 0 else "#d77b43", width=.65)
            ax.text(i, bottom + height + 100, f"{amount:,.0f}", ha="center", fontsize=10)
            if i != 4:
                running += amount
                ax.plot([i + .33, i + .67], [running, running], color="#8493a3", linewidth=.8)
        ax.set_xticks(range(5), ["Gross", "Trading\nfees", "Degradation", "Execution\n+ O&M", "Net"])
        ax.set(title=label, ylabel="EUR", ylim=(0, max(amounts[0], amounts[-1]) * 1.16))
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Where gross arbitrage profit goes\n" + note, fontsize=12)
    save(fig, "gross_to_net")

    fig, axes = plt.subplots(2, 2, figsize=(11, 7), layout="constrained")
    metrics = [("maximum_drawdown_eur", "Maximum drawdown", "EUR"),
               ("empirical_cvar_loss_eur", "95% empirical daily-loss CVaR", "EUR"),
               ("discharge_throughput_mwh", "Discharged energy", "MWh")]
    for ax, (key, title, unit) in zip(axes.flat, metrics):
        values = [base["comparison"][name][key] for name in names]
        ax.bar(labels, values, color=colors, width=.5)
        for i, value in enumerate(values):
            ax.annotate(f"{value:.2f}", (i, value), xytext=(0, 5), textcoords="offset points", ha="center")
        ax.set(title=title, ylabel=unit, ylim=(0, max(values) * 1.25))
        ax.spines[["top", "right"]].set_visible(False)
    uncertainty = base["uncertainty"]["paired_days"]
    low, high = uncertainty["mean_daily_difference_ci_eur"]
    mean = uncertainty["mean_daily_difference_eur"]
    ax = axes[1, 1]
    ax.axvline(0, color="#8c97a3", linestyle="--", label="No difference")
    ax.errorbar(mean, 0, xerr=np.array([[mean-low], [high-mean]]), fmt="o", color=colors[1], capsize=7)
    ax.set(yticks=[], xlabel="CVaR minus risk-neutral (EUR/day)", title="Mean net-profit difference: 95% interval", ylim=(-1, 1))
    ax.text(.5, .8, f"Mean {mean:.2f}; interval [{low:.2f}, {high:.2f}]", transform=ax.transAxes, ha="center")
    ax.text(.5, .15, "Includes zero: superiority not established\nPaired iid-day bootstrap; ignores serial dependence", transform=ax.transAxes, ha="center", fontsize=9)
    fig.suptitle("Risk and trading activity under identical costs\n" + note, fontsize=12)
    save(fig, "risk_and_uncertainty")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", default="docs/commercial_results/summary.json")
    parser.add_argument("--output-dir", default="docs/commercial_results")
    args = parser.parse_args()
    plot_summary(json.loads(Path(args.summary).read_text(encoding="utf-8")), args.output_dir)


if __name__ == "__main__":
    main()
