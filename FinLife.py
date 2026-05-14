"""
财务人生模拟器 - 入口程序
==========================
用法:
    python test.py                        # 默认读取 life_config.txt
    python test.py my_plan.txt            # 指定配置文件
    python test.py --config my_plan.txt   # 同上
"""

import sys
import argparse
from lifeclass import MonteCarloSim
from config_parser import parse_config, create_sim_from_config, get_sim_config


def main():
    # ---- 命令行参数 ----
    parser = argparse.ArgumentParser(description="财务人生模拟器")
    parser.add_argument("config_file", nargs="?", default="life_config.txt",
                        help="配置文件路径 (默认: life_config.txt)")
    parser.add_argument("--config", dest="config_file_alt",
                        help="配置文件路径 (同位置参数)")
    args = parser.parse_args()
    config_path = args.config_file_alt or args.config_file

    # ---- 解析配置 ----
    print(f"📖 读取配置文件: {config_path}")
    config = parse_config(config_path)
    sim_params = get_sim_config(config)

    # ---- 模拟器工厂函数 ----
    def create_sim():
        return create_sim_from_config(config)

    # ---- 1. 蒙特卡洛模拟 ----
    print(f"🎲 运行蒙特卡洛模拟 ({sim_params['n_samples']} 样本) ...")
    mc = MonteCarloSim(create_sim, n_samples=sim_params['n_samples'], seed=sim_params['seed'])
    mc.run(end_year=sim_params['end_year'])
    print("✅ 蒙特卡洛模拟完成")

    # ---- 2. 单次确定性模拟 ----
    det = create_sim()
    det.run(sim_params['end_year'])
    print("\n=== 确定性模拟最终状态 ===")
    print(f"  净值: {det.net_worth/1e4:.1f} 万")
    print(f"  总资产: {det.total_assets/1e4:.1f} 万")
    print(f"  现金: {det.cash/1e4:.1f} 万")
    print(f"  投资: {det.investments/1e4:.1f} 万")
    print(f"  房产: {det.real_estate/1e4:.1f} 万")
    print(f"  负债: {det.liabilities/1e4:.1f} 万")

    # ---- 3. 蒙特卡洛统计 ----
    stats = mc.summary()
    idx = -1
    print("\n=== 蒙特卡洛模拟统计 ({0}年) ===".format(int(stats['years'][idx])))
    print(f"  均值净值: {stats['mean'][idx]/1e4:.1f} 万")
    print(f"  中位数净值: {stats['p50'][idx]/1e4:.1f} 万")
    print(f"  5% 分位: {stats['p5'][idx]/1e4:.1f} 万")
    print(f"  95% 分位: {stats['p95'][idx]/1e4:.1f} 万")

    # ---- 4. 事件日志 ----
    sample = mc.results[0]
    print("\n=== 事件日志 (样本1) ===")
    for e in sample.event_log:
        print(f"  {e['year']}年: [{e['event']}] {e['detail']}")

    # ---- 5. 财务自由概率 ----
    fi_prob = mc.find_financial_independence_year(threshold_rate=0.04, expense_multiple=25)
    years = stats["years"]
    print("\n=== 财务自由概率（投资 ≥ 25× 年生活费） ===")
    for y, p in zip(years, fi_prob):
        if y % 5 == 0 and p > 0.01:
            print(f"  {int(y)}年: {p*100:.1f}%")

    # ---- 6. 可视化 ----
    print("\n📊 生成图表...")
    mc.plot(title="Net Worth Projection")
    mc.plot_assets_breakdown()
    mc.plot_income_expense()

    import matplotlib.pyplot as plt
    plt.show()

    print("\n✅ All OK!")

    return mc, det


if __name__ == "__main__":
    mc, det = main()
