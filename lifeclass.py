"""
财务人生模拟器 - Financial Life Simulator
==========================================
功能：
  1. 模拟完整的资产负债表（现金/投资/房产/负债）
  2. 模拟收入支出表（工资/投资收益/生活费/房贷/教育等）
  3. 事件驱动：不定期事件修改内部参数
  4. 支持一阶导参数：通胀率/工资增长率/资产收益率
  5. 支持蒙特卡洛模拟：参数服从分布

使用示例：
  sim = FinanceLifeSim(...)
  sim.add_event(...)
  result = sim.run(end_year=2060, n_samples=1000)
  result.plot()
"""
# TBD: Treat inflation

import numpy as np
from matplotlib import pyplot as plt
import copy
import gc


# ============================================================
#  Parameter: 带不确定性的参数
# ============================================================
class Parameter:
    """可指定为固定值或随机分布的参数。

    Examples
    --------
    >>> p1 = Parameter(120000, annual_change_rate=0.03)        # 固定，年增 3%
    >>> p2 = Parameter(0.06, dist_type="normal",
    ...                dist_params=(0.06, 0.02))                # 正态分布
    >>> val = p2.sample(year=5, rng=np.random.default_rng(42))
    """

    def __init__(self, value=0, dist_type="fixed", dist_params=None,
                 annual_change_rate=0.0):
        self.base_value = float(value)
        self.dist_type = dist_type
        self.dist_params = dist_params or ()
        self.annual_change_rate = float(annual_change_rate)

    # ---------- 采样 ----------
    def sample(self, rng=None):
        if rng is None:
            rng = np.random.default_rng()
        return self._draw(rng)

    def grow(self):
        self.change_value(self.base_value * (1+self.annual_change_rate))
        return

    def change_value(self, value):
        vold = self.base_value
        self.base_value = value
        if self.dist_type == "fixed":
            return
        elif self.dist_type in ["normal", "uniform"]:
            if isinstance(self.dist_params, list):
                self.dist_params = [params*(self.base_value/vold) for params in self.dist_params]
            elif isinstance(self.dist_params, tuple):
                dist_list = list(self.dist_params)
                dist_list = [params*(self.base_value/vold) for params in dist_list]
                self.dist_params = tuple(dist_list)
        else:
            raise ValueError(f"Unknown dist_type: {self.dist_type}")
        return

    def _draw(self, rng):
        if self.dist_type == "fixed":
            return self.base_value
        elif self.dist_type == "normal":
            mean, std = self.dist_params
            return float(rng.normal(mean, std))
        elif self.dist_type == "lognormal":
            mu, sigma = self.dist_params
            return float(np.exp(rng.normal(mu, sigma)))
        elif self.dist_type == "uniform":
            lo, hi = self.dist_params
            return float(rng.uniform(lo, hi))
        elif self.dist_type == "triangular":
            lo, mode, hi = self.dist_params
            return float(rng.triangular(lo, mode, hi))
        else:
            raise ValueError(f"Unknown dist_type: {self.dist_type}")

    # ---------- 期望值 ----------
    def expected(self, year=0):
        if self.dist_type == "fixed":
            return self.base_value
        elif self.dist_type == "normal":
            return self.dist_params[0]
        elif self.dist_type == "lognormal":
            mu, sigma = self.dist_params
            return np.exp(mu + sigma ** 2 / 2)
        elif self.dist_type == "uniform":
            lo, hi = self.dist_params
            return (lo + hi) / 2
        elif self.dist_type == "triangular":
            lo, mode, hi = self.dist_params
            return (lo + mode + hi) / 3
        return self.base_value


# ============================================================
#  LifeEvent: 事件驱动
# ============================================================
class LifeEvent:
    """在指定年份 / 条件下触发，通过回调函数修改模拟器内部状态。"""

    def __init__(self, name, trigger_year=None, trigger_cond=None,
                 max_times=1, callback=None, **kwargs):
        self.name = name
        self.trigger_year = trigger_year          # int | list[int] | None
        self.trigger_cond = trigger_cond          # fn(sim, year)->bool | None
        self.max_times = max_times
        self.callback = callback
        self.kwargs = kwargs
        self._fired = 0

    def should_trigger(self, sim, year):
        if self._fired >= self.max_times:
            return False
        if self.trigger_year is not None:
            years = (self.trigger_year if isinstance(self.trigger_year, (list, tuple))
                     else [self.trigger_year])
            if year in years:
                return True
        if self.trigger_cond is not None and self.trigger_cond(sim, year):
            return True
        return False

    def execute(self, sim):
        self._fired += 1
        if self.callback:
            self.callback(sim, **self.kwargs)



# ============================================================
#  FinanceLifeSim: 单条生命轨迹模拟器
# ============================================================
class FinanceLifeSim:
    """完整的单次财务人生模拟。

    Attributes
    ----------
    cash, investments, real_estate, other_assets : float
        资产各科目
    liabilities : float
        负债总额
    salary, living_expense, investment_return, ... : Parameter
        收支参数（均可设为随机分布 + 年增长率）
    """

    def __init__(self, init_cash=100_000, init_investments=50_000,
                 init_real_estate=0, init_other_assets=0,
                 init_liabilities=0,
                 salary=Parameter(150_000, annual_change_rate=0.03),
                 living_expense=Parameter(60_000, annual_change_rate=0.03),
                 investment_return=Parameter(0.06, dist_type="normal",
                                             dist_params=(0.06, 0.15)),
                 inflation_rate=Parameter(0.03, dist_type="normal", dist_params=(0.03, 0.02)),
                 start_year=2024):
        # --- 资产 ---
        self.cash = float(init_cash)
        self.investments = float(init_investments)
        self.real_estate = float(init_real_estate)
        self.other_assets = float(init_other_assets)
        self.house_appreciation_rate = 0.0
        # --- 负债 ---
        # --- 贷款 ---
        self.mortgages = []           # list[dict]
        self.car_loans = []
        self.liabilities = float(init_liabilities)
        # --- 参数 ---
        self.salary = salary
        self.living_expense = living_expense
        self.investment_return = investment_return
        self.inflation_rate = inflation_rate
        # --- 时间 ---
        self.start_year = start_year
        self.current_year = start_year
        self.inflation_factor = 1.0
        # --- 生活状态 ---
        self.retired = False
        self.child_count = 0
        self.children = []            # list[dict]
        # --- 事件 ---
        self.events = []
        self.event_log = []           # 已触发事件记录
        # --- 历史记录 ---
        self.history = self._empty_record()

    # ---------- 辅助 ----------
    @property
    def total_assets(self):
        return (self.cash + self.investments +
                self.real_estate + self.other_assets)

    @property
    def net_worth(self):
        return self.total_assets - self.liabilities

    @staticmethod
    def _empty_record():
        return dict(
            year=[], net_worth=[], cash=[], investments=[],
            real_estate=[], other_assets=[], liabilities=[],
            total_assets=[],
            income_salary=[], income_invest=[], income_other=[],
            total_income=[],
            expense_living=[], expense_mortgage=[], expense_car=[],
            expense_education=[], expense_other=[], total_expense=[],
            # 现金流
            cash_flow=[], inflation_factor=[],
        )

    # ---------- 事件管理 ----------
    def add_event(self, event):
        self.events.append(event)

    def _process_events(self):
        for evt in self.events:
            if evt.should_trigger(self, self.current_year):
                evt.execute(self)

    # ---------- 贷款还款 ----------
    def _pay_loans(self):
        """等额本息还款"""
        mortgage_pay = 0.0
        car_pay = 0.0
        for pool_name, pool in [("mortgages", self.mortgages),
                                 ("car_loans", self.car_loans)]:
            total_pay = 0.0
            remaining_loans = []
            for loan in pool:
                r = loan["remaining"]
                if r <= 0:
                    continue
                rate = loan["annual_rate"]
                years_left = max(1,
                    loan["total_years"] -
                    (self.current_year - loan["start_year"]))
                # 月还款额（等额本息）
                mr = rate / 12
                # Only need to pay for the capital when the interest rate is very low
                if mr < 1e-12:
                    monthly = r / (years_left * 12)
                else:
                    monthly = (r * mr * (1 + mr) ** (years_left * 12) /
                               ((1 + mr) ** (years_left * 12) - 1))
                # 累加一年 12 期
                year_pay = 0
                for _ in range(12):
                    interest = r * mr
                    principal = monthly - interest    # The principal get paideach month
                    principal = min(principal, r)
                    r -= principal
                    year_pay += monthly
                    if r <= 0.01:
                        break
                loan["remaining"] = max(r, 0)
                total_pay += year_pay
                if r > 0.01:
                    remaining_loans.append(loan)
            if pool_name == "mortgages":
                self.mortgages = remaining_loans
                mortgage_pay += total_pay
            else:
                self.car_loans = remaining_loans
                car_pay += total_pay
        return mortgage_pay, car_pay

    # ---------- 核心演化 ----------
    def _step(self, rng):
        """演化一年，使用 rng 进行随机采样"""
        # 1) 处理事件
        self._process_events()

        # Generate inflation rate
        inflation_rate = self.inflation_rate.sample(rng)
        self.inflation_factor *= (1+inflation_rate)

        # 2) 收入
        income_salary = self.salary.sample(rng)
        income_invest = self.investments * self.investment_return.sample(rng)
        income_other = 0.0
        total_income = income_salary + income_invest + income_other

        # 3) 支出
        expense_living = self.living_expense.sample(rng)

        # 还贷（等额本息，按月累计）
        mortgage_pay, car_pay = self._pay_loans()
        expense_mortgage = mortgage_pay
        expense_car = car_pay

        # 教育支出
        expense_education = 0.0
        for ch in self.children:
            child_age = self.current_year - ch["birth_year"]
            if child_age >= ch["edu_start_age"]:
                edu_years = 12  # 假设 12 年教育
                if child_age < ch["edu_start_age"] + edu_years:
                    # 教育费用也受通胀影响
                    edu_year_offset = child_age - ch["edu_start_age"]
                    growth = (1 + inflation_rate) ** edu_year_offset
                    expense_education += ch["edu_cost"] * growth

        expense_other = 0.0
        total_expense = (expense_living + expense_mortgage + expense_car +
                         expense_education + expense_other)

        # 4) 资产更新
        self.cash += income_salary - total_expense
        self.investments += income_invest

        # Make sure cash is not negative
        withdraw = min(self.investments, -min(self.cash, 0))
        self.investments -= withdraw
        self.cash += withdraw

        # 房产增值
        if self.house_appreciation_rate > 0 and self.real_estate > 0:
            self.real_estate *= (1 + self.house_appreciation_rate)

        # 负债更新
        self.liabilities = (sum(l["remaining"] for l in self.mortgages) +
                            sum(l["remaining"] for l in self.car_loans))

        # 车辆折旧（简化：每年 15%）
        if self.other_assets > 0:
            self.other_assets *= 0.85

        # Grow salary, expense and investment return
        self.salary.grow()
        self.living_expense.grow()

        # 5) 记录
        h = self.history
        h["year"].append(self.current_year)
        h["net_worth"].append(self.net_worth)
        h["cash"].append(self.cash)
        h["investments"].append(self.investments)
        h["real_estate"].append(self.real_estate)
        h["other_assets"].append(self.other_assets)
        h["liabilities"].append(self.liabilities)
        h["total_assets"].append(self.total_assets)
        h["income_salary"].append(income_salary)
        h["income_invest"].append(income_invest)
        h["income_other"].append(income_other)
        h["total_income"].append(total_income)
        h["expense_living"].append(expense_living)
        h["expense_mortgage"].append(expense_mortgage)
        h["expense_car"].append(expense_car)
        h["expense_education"].append(expense_education)
        h["expense_other"].append(expense_other)
        h["total_expense"].append(total_expense)
        h["cash_flow"].append(total_income - total_expense)
        h["inflation_factor"].append(self.inflation_factor)

        self.current_year += 1

    def run(self, end_year, rng=None):
        """运行单次模拟，返回 self（可直接访问 .history）"""
        if rng is None:
            rng = np.random.default_rng()
        while self.current_year <= end_year:
            self._step(rng)
        # numpy 化
        for k, v in self.history.items():
            self.history[k] = np.array(v)
        return self


# ============================================================
#  MonteCarloSim: 蒙特卡洛批量模拟
# ============================================================
class MonteCarloSim:
    """批量运行 FinanceLifeSim 以获得分布统计。"""

    def __init__(self, sim_factory, n_samples=1000, seed=42):
        """
        sim_factory : callable() -> FinanceLifeSim
            每次调用返回一个全新的模拟器实例（可引用共享的事件列表等）
        n_samples : int
        seed : int
        """
        self.sim_factory = sim_factory
        self.n_samples = n_samples
        self.seed = seed
        self.results = []   # list[FinanceLifeSim]

    def run(self, end_year):
        master_rng = np.random.default_rng(self.seed)
        for i in range(self.n_samples):
            sim = copy.deepcopy(self.sim_factory())
            child_seed = master_rng.integers(0, 2**63)
            sim.run(end_year, rng=np.random.default_rng(child_seed))
            self.results.append(sim)
        return self

    # ---------- 统计量 ----------
    def net_worth_matrix(self, inflation=True):
        """(n_samples, n_years)"""
        if inflation:
            return np.vstack([s.history["net_worth"] for s in self.results])
        else:
            return np.vstack([s.history["net_worth"] / s.history["inflation_factor"] for s in self.results])

    def summary(self, percentiles=[5, 25, 50, 75, 95]):
        nw = self.net_worth_matrix()
        nw_noinf = self.net_worth_matrix(inflation=False)
        stats = {}
        for p in percentiles:
            stats[f"p{p}"] = np.percentile(nw, p, axis=0)
            stats[f"p{p}_noinf"] = np.percentile(nw_noinf, p, axis=0)
        stats["mean"] = nw.mean(axis=0)
        stats["std"] = nw.std(axis=0)
        stats["mean_noinf"] = nw_noinf.mean(axis=0)
        stats["std_noinf"] = nw_noinf.std(axis=0)
        stats["years"] = self.results[0].history["year"]
        return stats

    # ---------- 可视化 ----------
    def plot(self, percentiles=[5, 25, 50, 75, 95],
             show_individual=False, max_individual=50,
             title="Net Worth Projection", figsize=(14, 7),
             unit="W", inflation=True):
        stats = self.summary(percentiles)
        years = stats["years"]
        divisor = 1e4 if unit == "W" else 1

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize,
                                         gridspec_kw={"height_ratios": [3, 1]},
                                         sharex=True)
        # --- 上图：净值 ---
        if show_individual:
            if inflation:
                nw = self.net_worth_matrix()
            else:
                nw = self.net_worth_matrix(inflation=False)
            for i in range(min(max_individual, nw.shape[0])):
                ax1.plot(years, nw[i] / divisor, color="steelblue",
                         alpha=0.03, linewidth=0.5)

        if not inflation:
            namesuffix = '_noinf'
        else:
            namesuffix = ''
        p5name = 'p5' + namesuffix
        p95name = 'p95' + namesuffix
        p25name = 'p25' + namesuffix
        p75name = 'p75' + namesuffix
        p50name = 'p50' + namesuffix
        meanname = 'mean' + namesuffix

        ax1.fill_between(years, stats[p5name] / divisor, stats[p95name] / divisor,
                          alpha=0.15, color="steelblue", label="90% CI")
        ax1.fill_between(years, stats[p25name] / divisor, stats[p75name] / divisor,
                          alpha=0.25, color="steelblue", label="IQR (p25-p75)")
        ax1.plot(years, stats[p50name] / divisor, "b-", lw=2, label="Median")
        ax1.plot(years, stats[meanname] / divisor, "r--", lw=1.5, label="Mean")
        ax1.axhline(0, color="black", lw=0.8, ls="--")
        ax1.set_ylabel(f"Net Worth ({unit})")
        ax1.legend(loc="upper left")
        ax1.set_title(title)
        ax1.grid(True, alpha=0.3)

        # --- 下图：年均现金流（取中位数那条路径）---
        median_idx = np.argmin(np.abs(
            np.array([np.median(s.history["net_worth"][-1])
                      for s in self.results]) -
            np.median(stats["p50"][-1])
        ))
        median_sim = self.results[median_idx]
        h = median_sim.history
        income = h["total_income"] / divisor
        expense = h["total_expense"] / divisor
        ax2.bar(years, income, width=0.8, color="green", alpha=0.6,
                label="Income")
        ax2.bar(years, -expense, width=0.8, color="red", alpha=0.6,
                label="Expense")
        ax2.axhline(0, color="black", lw=0.8)
        ax2.set_ylabel(f"Cash Flow ({unit})")
        ax2.set_xlabel("Year")
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        return fig

    def plot_assets_breakdown(self, sim_index=-1, unit="W", figsize=(14, 5)):
        """绘制某条路径的资产结构堆叠图"""
        s = self.results[sim_index]
        h = s.history
        d = 1e4 if unit == "W" else 1
        years = h["year"]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, sharey=True)
        # 资产堆叠
        ax1.stackplot(years,
                       h["cash"]/d, h["investments"]/d,
                       h["real_estate"]/d, h["other_assets"]/d,
                       labels=["Cash", "Investments", "Real Estate", "Other"],
                       alpha=0.8)
        ax1.set_title("Assets Breakdown")
        ax1.set_ylabel(f"Amount ({unit})")
        ax1.legend(loc="upper left")
        ax1.grid(True, alpha=0.3)
        # 净值 vs 负债
        ax2.fill_between(years, 0, h["net_worth"]/d,
                          color="steelblue", alpha=0.5, label="Net Worth")
        ax2.fill_between(years, h["net_worth"]/d, h["total_assets"]/d,
                          color="tomato", alpha=0.5, label="Liabilities")
        ax2.set_title("Net Worth & Liabilities")
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        return fig

    def plot_income_expense(self, sim_index=-1, unit="W", figsize=(14, 5)):
        """绘制某条路径的收入支出明细"""
        s = self.results[sim_index]
        h = s.history
        d = 1e4 if unit == "W" else 1
        years = h["year"]
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
        # 收入
        ax1.stackplot(years,
                       h["income_salary"]/d, h["income_invest"]/d,
                       h["income_other"]/d,
                       labels=["Salary", "Investment", "Other"],
                       alpha=0.8, colors=["#2ca02c", "#1f77b4", "#ff7f0e"])
        ax1.set_title("Income")
        ax1.set_ylabel(f"Amount ({unit})")
        ax1.legend(loc="upper left")
        ax1.grid(True, alpha=0.3)
        # 支出
        ax2.stackplot(years,
                       h["expense_living"]/d, h["expense_mortgage"]/d,
                       h["expense_car"]/d, h["expense_education"]/d,
                       h["expense_other"]/d,
                       labels=["Living", "Mortgage", "Car", "Education", "Other"],
                       alpha=0.8, colors=["#d62728", "#9467bd", "#8c564b",
                                          "#e377c2", "#7f7f7f"])
        ax2.set_title("Expense")
        ax2.legend(loc="upper left")
        ax2.grid(True, alpha=0.3)
        plt.tight_layout()
        return fig

    def find_financial_independence_year(self, threshold_rate=0.04,
                                          expense_multiple=25):
        """估算财务自由年份：当投资资产 >= 年生活支出 × multiple 时"""
        counts = np.zeros(self.results[0].history["year"].shape[0])
        for s in self.results:
            h = s.history
            inv = h["investments"]
            exp = h["expense_living"]
            fi = inv >= exp * expense_multiple
            # 找到首次满足的年份
            idx = np.where(fi)[0]
            if len(idx) > 0:
                counts[idx[0]:] += 1
        pct = counts / len(self.results)
        return pct
