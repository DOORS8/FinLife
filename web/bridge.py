"""
bridge.py — Pyodide bridge: exposes simulation runner to JavaScript.
Loaded into Pyodide's virtual filesystem alongside lifeclass.py,
config_parser.py, and events_factory.py.
"""
import io
import base64
import copy
import numpy as np

from matplotlib import pyplot as plt

from config_parser import parse_config, create_sim_from_config, get_sim_config
from lifeclass import MonteCarloSim


def _run(config_text, n_samples):
    """Run the full simulation pipeline and return JSON-serializable dict."""
    # ── Config ──
    with open('/tmp/life_config.txt', 'w') as f:
        f.write(config_text)
    config = parse_config('/tmp/life_config.txt')
    sim_params = get_sim_config(config)
    sim_params['n_samples'] = n_samples
    seed = sim_params.get('seed', 42)

    # Inflation-adjust flag
    raw = sim_params['inflation_adjusted']
    use_real = str(raw).lower() in ('true', '1', 'yes')

    # ── Factory ──
    def create_sim():
        return create_sim_from_config(config)

    # ── Monte Carlo ──
    mc = MonteCarloSim(create_sim, n_samples=n_samples, seed=seed)
    mc.run(end_year=sim_params['end_year'])

    # ── Deterministic ──
    det = create_sim_from_config(config)
    det.run(sim_params['end_year'])

    # ── Gather stats ──
    stats = mc.summary()
    years = [int(y) for y in stats["years"]]
    suffix = "_noinf" if use_real else ""

    mc_stats = {
        "years": years,
        "mean": [round(float(v / 1e4), 1) for v in stats["mean" + suffix]],
        "p50":  [round(float(v / 1e4), 1) for v in stats["p50" + suffix]],
        "p5":   [round(float(v / 1e4), 1) for v in stats["p5" + suffix]],
        "p95":  [round(float(v / 1e4), 1) for v in stats["p95" + suffix]],
    }

    det_stats = {
        "net_worth":     round(float(det.net_worth / 1e4), 1),
        "total_assets":  round(float(det.total_assets / 1e4), 1),
        "cash":          round(float(det.cash / 1e4), 1),
        "investments":   round(float(det.investments / 1e4), 1),
        "real_estate":   round(float(det.real_estate / 1e4), 1),
        "liabilities":   round(float(det.liabilities / 1e4), 1),
    }

    # ── Event log (sample 0) ──
    event_log = [
        {"year": e["year"], "event": e["event"], "detail": e["detail"]}
        for e in mc.results[0].event_log
    ]

    # ── FI probability ──
    fi_prob = mc.find_financial_independence_year(
        threshold_rate=0.04, expense_multiple=25
    )
    fi_table = []
    for y, p in zip(years, fi_prob):
        if y % 5 == 0 and p > 0.01:
            fi_table.append({"year": y, "prob": round(p * 100, 1)})

    # ── Plots (base64 PNG) ──
    plt.rcParams['figure.dpi'] = 100

    plots = {}
    plot_fns = [
        ("net_worth",        lambda: mc.plot(title="Net Worth Projection",
                                              inflation=not use_real)),
        ("assets_breakdown", lambda: mc.plot_assets_breakdown(
                                              inflation=not use_real)),
        ("income_expense",   lambda: mc.plot_income_expense(
                                              inflation=not use_real)),
        ("financial_freedom",lambda: mc.plot_financial_freedom()),
    ]
    for name, fn in plot_fns:
        fig = fn()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        plt.close(fig)
        buf.seek(0)
        plots[name] = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    return {
        "det_stats": det_stats,
        "mc_stats": mc_stats,
        "event_log": event_log,
        "fi_table": fi_table,
        "plots": plots,
    }


def _run_compare(config_texts, labels, n_samples):
    """Run multiple configs and produce comparison results.

    config_texts : list[str]  — 2~5 INI config texts
    labels       : list[str]  — short labels for each config
    n_samples    : int        — MC sample count
    """
    if len(config_texts) < 2 or len(config_texts) > 5:
        raise ValueError("compare requires 2~5 configs")

    palette = [
        ("steelblue",   "dodgerblue"),
        ("darkorange",  "orange"),
        ("forestgreen", "limegreen"),
        ("crimson",     "salmon"),
        ("purple",      "mediumpurple"),
    ]

    mc_list = []
    infl_flags = []
    per_config_stats = []

    for i, (text, label) in enumerate(zip(config_texts, labels)):
        with open(f'/tmp/compare_{i}.txt', 'w') as f:
            f.write(text)
        config = parse_config(f'/tmp/compare_{i}.txt')
        sim_params = get_sim_config(config)
        raw = sim_params['inflation_adjusted']
        use_real = str(raw).lower() in ('true', '1', 'yes')
        infl_flags.append(use_real)

        # Use default-arg capture to bind config for this iteration
        def create_sim(_config=config):
            return create_sim_from_config(_config)

        mc = MonteCarloSim(create_sim, n_samples=n_samples,
                           seed=sim_params.get('seed', 42))
        mc.run(end_year=sim_params['end_year'])

        suffix = '_noinf' if use_real else ''
        stats = mc.summary()
        years = [int(y) for y in stats["years"]]
        mc_stats = {
            "years": years,
            "mean":  [round(float(v / 1e4), 1) for v in stats["mean" + suffix]],
            "p50":   [round(float(v / 1e4), 1) for v in stats["p50" + suffix]],
            "p5":    [round(float(v / 1e4), 1) for v in stats["p5" + suffix]],
            "p95":   [round(float(v / 1e4), 1) for v in stats["p95" + suffix]],
        }
        per_config_stats.append({
            "label": label,
            "mc_stats": mc_stats,
        })
        mc_list.append(mc)

    # Inflation consistency check
    use_real = all(infl_flags) if all(f == infl_flags[0] for f in infl_flags) else False
    suffix = '_noinf' if use_real else ''

    # ── Comparison plot ──
    plt.rcParams['figure.dpi'] = 100
    fig, ax = plt.subplots(figsize=(14, 7))
    divisor = 1e4

    for i, mc in enumerate(mc_list):
        stats = mc.summary()
        years = stats["years"]
        fill_color, line_color = palette[i % len(palette)]
        label = labels[i]

        ax.fill_between(years,
                        stats["p5" + suffix] / divisor,
                        stats["p95" + suffix] / divisor,
                        alpha=0.10, color=fill_color)
        ax.fill_between(years,
                        stats["p25" + suffix] / divisor,
                        stats["p75" + suffix] / divisor,
                        alpha=0.20, color=fill_color,
                        label=f"{label} (IQR)")
        ax.plot(years, stats["p50" + suffix] / divisor,
                color=line_color, lw=2,
                label=f"{label} Median")
        ax.plot(years, stats["mean" + suffix] / divisor,
                color=line_color, lw=1.2, ls="--",
                label=f"{label} Mean")

    ax.set_yscale('log')
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_ylabel("Net Worth (W)")
    ax.set_xlabel("Year")
    ax.set_title("Net Worth Projection — Comparison")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    plt.close(fig)
    buf.seek(0)
    compare_plot = "data:image/png;base64," + base64.b64encode(buf.read()).decode()

    return {
        "per_config": per_config_stats,
        "compare_plot": compare_plot,
    }
