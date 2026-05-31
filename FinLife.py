"""
财务人生模拟器 - 入口程序
==========================
用法:
    python test.py                        # 默认读取 life_config.txt
    python test.py my_plan.txt            # 指定配置文件
    python test.py --config my_plan.txt   # 同上
    python test.py --compare c1.txt c2.txt c3.txt   # 对比多个配置的财富增长曲线
"""

import sys
import os
import argparse
import numpy as np
from matplotlib import pyplot as plt
from lifeclass import MonteCarloSim
from config_parser import parse_config, create_sim_from_config, get_sim_config

# ──────────────────────────────────────────
# 公共函数
# ──────────────────────────────────────────

def run_single(config_path):
    """读取配置并运行蒙特卡洛模拟，返回 (mc, sim_params)"""
    print(f"📖 读取配置文件: {config_path}")
    config = parse_config(config_path)
    sim_params = get_sim_config(config)

    def create_sim():
        return create_sim_from_config(config)

    print(f"🎲 运行蒙特卡洛模拟 ({sim_params['n_samples']} 样本) ...")
    mc = MonteCarloSim(create_sim, n_samples=sim_params['n_samples'],
                       seed=sim_params['seed'])
    mc.run(end_year=sim_params['end_year'])

    # 通胀调整标识
    raw = sim_params['inflation_adjusted']
    sim_params['inflation_adjusted'] = raw.lower() in ('true', '1', 'yes')

    print(f"✅ {config_path} 模拟完成")
    return mc, sim_params


def print_single_results(mc, sim_params, det=None):
    """打印单个配置的模拟结果"""
    use_real = sim_params['inflation_adjusted']
    suffix = '_noinf' if use_real else ''

    if det is not None:
        print("\n=== 确定性模拟最终状态 ===")
        print(f"  净值: {det.net_worth/1e4:.1f} 万")
        print(f"  总资产: {det.total_assets/1e4:.1f} 万")
        print(f"  现金: {det.cash/1e4:.1f} 万")
        print(f"  投资: {det.investments/1e4:.1f} 万")
        print(f"  房产: {det.real_estate/1e4:.1f} 万")
        print(f"  负债: {det.liabilities/1e4:.1f} 万")

    stats = mc.summary()
    idx = -1
    adj_label = " (排除通胀)" if use_real else ""
    print(f"\n=== 蒙特卡洛模拟统计 ({int(stats['years'][idx])}年){adj_label} ===")
    print(f"  均值净值: {stats['mean'+suffix][idx]/1e4:.1f} 万")
    print(f"  中位数净值: {stats['p50'+suffix][idx]/1e4:.1f} 万")
    print(f"  5% 分位: {stats['p5'+suffix][idx]/1e4:.1f} 万")
    print(f"  95% 分位: {stats['p95'+suffix][idx]/1e4:.1f} 万")

    sample = mc.results[0]
    print("\n=== 事件日志 (样本1) ===")
    for e in sample.event_log:
        print(f"  {e['year']}年: [{e['event']}] {e['detail']}")

    fi_prob = mc.find_financial_independence_year(
        threshold_rate=0.04, expense_multiple=25)
    years = stats["years"]
    print("\n=== 财务自由概率（投资 ≥ 25× 年生活费） ===")
    for y, p in zip(years, fi_prob):
        if y % 5 == 0 and p > 0.01:
            print(f"  {int(y)}年: {p*100:.1f}%")


# ──────────────────────────────────────────
# 对比模式绘图
# ──────────────────────────────────────────

def plot_compare(config_paths, mc_list, inflation=True):
    """
    对比多个配置的财富增长曲线（净值分位数图）。
    每个配置用不同颜色，展示 p5-p95 带 + p25-p75 带 + p50 中位线 + mean 均值线。
    最多 5 个配置。
    inflation : bool
        True 表示名义值, False 表示排除通胀（实际购买力）
    """
    # 预定义 5 种对比色 (填充色, 线色)
    palette = [
        ("steelblue",   "dodgerblue"),
        ("darkorange",  "orange"),
        ("forestgreen", "limegreen"),
        ("crimson",     "salmon"),
        ("purple",      "mediumpurple"),
    ]

    fig, ax = plt.subplots(figsize=(14, 7))
    divisor = 1e4
    suffix = '' if inflation else '_noinf'

    for i, (cfg_path, mc) in enumerate(zip(config_paths, mc_list)):
        stats = mc.summary()
        years = stats["years"]
        fill_color, line_color = palette[i % len(palette)]

        # 提取短文件名（去掉目录和扩展名）作为图例标签
        label = os.path.splitext(os.path.basename(cfg_path))[0]

        # p5-p95 带状区间（浅色）
        ax.fill_between(years,
                        stats["p5"+suffix] / divisor,
                        stats["p95"+suffix] / divisor,
                        alpha=0.10, color=fill_color)
        # p25-p75 带状区间（中色）
        ax.fill_between(years,
                        stats["p25"+suffix] / divisor,
                        stats["p75"+suffix] / divisor,
                        alpha=0.20, color=fill_color,
                        label=f"{label} (IQR)")
        # p50 中位数线
        ax.plot(years, stats["p50"+suffix] / divisor,
                color=line_color, lw=2,
                label=f"{label} Median")
        # mean 均值线
        ax.plot(years, stats["mean"+suffix] / divisor,
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
    return fig


# ──────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────

def main():
    # ---- 命令行参数 ----
    parser = argparse.ArgumentParser(description="财务人生模拟器")
    parser.add_argument("config_file", nargs="?", default="life_config.txt",
                        help="配置文件路径 (默认: life_config.txt)")
    parser.add_argument("--config", dest="config_file_alt",
                        help="配置文件路径 (同位置参数)")
    parser.add_argument("--compare", nargs="+", metavar="CONFIG",
                        help="对比模式: 指定 2~5 个配置文件，对比财富增长曲线")
    args = parser.parse_args()

    # ──── 对比模式 ────
    if args.compare:
        paths = args.compare
        if len(paths) < 2:
            print("⚠️  --compare 至少需要 2 个配置文件")
            sys.exit(1)
        if len(paths) > 5:
            print("⚠️  --compare 最多支持 5 个配置文件，已截断为前 5 个")
            paths = paths[:5]

        mc_list = []
        infl_flags = []
        for p in paths:
            mc, sp = run_single(p)
            mc_list.append(mc)
            infl_flags.append(sp['inflation_adjusted'])

        # 如果所有配置的 inflation_adjusted 一致，统一使用；否则使用名义值
        use_real = all(infl_flags) if all(f == infl_flags[0] for f in infl_flags) else False
        if not use_real and any(infl_flags):
            print("⚠️  各配置文件 inflation_adjusted 设置不一致，统一使用名义值绘图")

        print("\n📊 生成对比图...")
        plot_compare(paths, mc_list, inflation=not use_real)
        plt.show()
        print("\n✅ All OK!")
        return

    # ──── 单配置模式（原有逻辑不变） ────
    config_path = args.config_file_alt or args.config_file
    mc, sim_params = run_single(config_path)

    # 确定性模拟
    config = parse_config(config_path)
    det = create_sim_from_config(config)
    det.run(sim_params['end_year'])

    print_single_results(mc, sim_params, det)

    # 可视化
    print("\n📊 生成图表...")
    # inflation_adjusted=True 表示用实际购买力（排除通胀），对应 net_worth_matrix(inflation=False)
    use_real = sim_params['inflation_adjusted']
    mc.plot(title="Net Worth Projection", inflation=not use_real)
    mc.plot_assets_breakdown(inflation=not use_real)
    mc.plot_income_expense(inflation=not use_real)
    mc.plot_financial_freedom()
    plt.show()

    print("\n✅ All OK!")


if __name__ == "__main__":
    main()