from lifeclass import *
import copy
# ---------- 预置事件工厂 ----------

def make_buy_house(name="buy_house", trigger_year=2028,
                   house_price=3_000_000, down_pct=0.30,
                   mortgage_years=30, mortgage_rate=0.049,
                   appreciation=0.03):
    """买房事件"""
    def _cb(sim, **kw):
        down = kw["house_price"] * kw["down_pct"]
        loan = kw["house_price"] - down
        sim.cash -= down
        sim.real_estate += kw["house_price"]
        sim.liabilities += loan
        sim.mortgages.append(dict(
            remaining=loan, annual_rate=kw["mortgage_rate"],
            total_years=kw["mortgage_years"],
            start_year=sim.current_year,
        ))
        sim.house_appreciation_rate = kw["appreciation"]
        sim.event_log.append(dict(
            year=sim.current_year, event="buy_house",
            detail=f"买房 {kw['house_price']/1e4:.0f}W  "
                   f"首付{down/1e4:.0f}W  贷款{loan/1e4:.0f}W"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     house_price=house_price, down_pct=down_pct,
                     mortgage_years=mortgage_years,
                     mortgage_rate=mortgage_rate,
                     appreciation=appreciation)


def make_buy_car(name="buy_car", trigger_year=2025,
                 car_price=200_000, down_pct=0.50,
                 loan_years=3, loan_rate=0.05):
    """买车事件"""
    def _cb(sim, **kw):
        down = kw["car_price"] * kw["down_pct"]
        loan = kw["car_price"] - down
        sim.cash -= down
        sim.other_assets += kw["car_price"]
        sim.liabilities += loan
        sim.car_loans.append(dict(
            remaining=loan, annual_rate=kw["loan_rate"],
            total_years=kw["loan_years"],
            start_year=sim.current_year,
        ))
        sim.event_log.append(dict(
            year=sim.current_year, event="buy_car",
            detail=f"买车 {kw['car_price']/1e4:.0f}W"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     car_price=car_price, down_pct=down_pct,
                     loan_years=loan_years, loan_rate=loan_rate)


def make_job_change(name="job_change", trigger_year=2027,
                    new_salary=None, raise_pct=None, raise_value=None):
    """跳槽 / 涨薪

    参数说明（new_salary / raise_value 均按**当前购买力**输入，程序自动通胀换算）：
      - new_salary : Parameter — 以当前薪资水平预估的新工作薪资（分布），自动通胀到触发年份
      - raise_pct  : float — 涨薪比例（如 0.20 表示涨 20%），不受通胀影响，原样使用
      - raise_value: float — 以当前购买力预估的涨薪绝对值，自动通胀到触发年份
    """
    def _cb(sim, **kw):
        ns = kw["new_salary"]
        rp = kw["raise_pct"]
        rv = kw["raise_value"]
        # 用累计通胀因子将"当前购买力"换算为触发年份的名义值
        inflate = sim.inflation_factor
        if rp is not None:
            new_value = sim.salary.base_value * (1 + rp)
            sim.salary.change_value(new_value)
        elif rv is not None:
            sim.salary.change_value(sim.salary.base_value + rv * inflate)
        else:
            if isinstance(ns, Parameter):
                cr = sim.salary.annual_change_rate
                ns = copy.deepcopy(ns)
                ns.base_value *= inflate
                if ns.dist_type == "normal":
                    m, s = ns.dist_params
                    ns.dist_params = (m * inflate, s * inflate)
                ns.annual_change_rate = cr
                sim.salary = ns
        sim.event_log.append(dict(
            year=sim.current_year, event="job_change",
            detail=f"涨薪，薪资≈{sim.salary.base_value/1e4:.1f}W/年"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     new_salary=new_salary, raise_pct=raise_pct, raise_value=raise_value)


def make_marriage(name="marriage", trigger_year=2026,
                  partner_income=80_000, extra_expense=30_000):
    """结婚：增加配偶收入 + 共同支出

    partner_income 和 extra_expense 均按**当前购买力**输入，程序自动通胀换算到触发年份。
    """
    def _cb(sim, **kw):
        pi = kw["partner_income"] * sim.inflation_factor
        ee = kw["extra_expense"] * sim.inflation_factor
        sim.salary.base_value += pi
        if sim.salary.dist_type == "normal":
            m, s = sim.salary.dist_params
            sim.salary.dist_params = (m + pi, s * (1 + pi / m))
        sim.living_expense.base_value += ee
        sim.event_log.append(dict(
            year=sim.current_year, event="marriage",
            detail=f"结婚  家庭收入+{pi/1e4:.0f}W  "
                   f"支出+{ee/1e4:.1f}W"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     partner_income=partner_income,
                     extra_expense=extra_expense)


def make_birth(name="birth", trigger_year=2027,
               child_cost=30_000, edu_start_age=6,
               edu_cost=50_000):
    """生子

    child_cost / edu_cost 均按**当前购买力**输入，程序自动通胀换算到触发年份。
    edu_start_age 不受通胀影响。
    """
    def _cb(sim, **kw):
        cc = kw["child_cost"] * sim.inflation_factor
        ec = kw["edu_cost"] * sim.inflation_factor
        sim.child_count += 1
        sim.living_expense.change_value(sim.living_expense.base_value + cc)
        sim.children.append(dict(
            birth_year=sim.current_year,
            edu_start_age=kw["edu_start_age"],
            edu_cost=ec,
        ))
        sim.event_log.append(dict(
            year=sim.current_year, event="birth",
            detail=f"生子  年支出+{cc/1e4:.1f}W"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     child_cost=child_cost,
                     edu_start_age=edu_start_age,
                     edu_cost=edu_cost)


def make_retirement(name="retirement", trigger_year=2050):
    """退休"""
    def _cb(sim, **kw):
        sim.salary = Parameter(0)
        sim.living_expense.base_value *= 0.7
        sim.retired = True
        sim.event_log.append(dict(
            year=sim.current_year, event="retirement",
            detail="退休  工资归零  生活费→70%"
        ))
    return LifeEvent(name, trigger_year=trigger_year, callback=_cb)


def make_redistribute_invest(name='invest', trigger_year=2025):
    """ Every year put some amount of the cash to investment """
    def _cb(sim, **kw):
        total_expense = sim.history["total_expense"]
        if (len(total_expense)>0):
            total_investable = sim.cash+sim.investments
            if total_investable > total_expense[-1]:
                sim.cash = total_expense[-1]
                sim.investments = total_investable - total_expense[-1]
            else:
                sim.cash = total_investable
                sim.investments = 0

    return LifeEvent(name, trigger_year=trigger_year, callback=_cb)

def change_living_expense(name="change_expense", trigger_year=2027,
                    new_expense=None, raise_pct=None, raise_value=None):
    """更改生活成本（如搬家到不同城市）

    new_expense / raise_value 均按**当前购买力**输入，程序自动通胀换算到触发年份。
    raise_pct 不受通胀影响，原样使用。
    """
    def _cb(sim, **kw):
        ne = kw["new_expense"]
        rp = kw["raise_pct"]
        rv = kw["raise_value"]
        inflate = sim.inflation_factor
        if rp is not None:
            new_value = sim.living_expense.base_value * (1 + rp)
            sim.living_expense.change_value(new_value)
        elif rv is not None:
            sim.living_expense.change_value(sim.living_expense.base_value + rv * inflate)
        else:
            if isinstance(ne, Parameter):
                cr = sim.living_expense.annual_change_rate
                ne = copy.deepcopy(ne)
                ne.base_value *= inflate
                if ne.dist_type == "normal":
                    m, s = ne.dist_params
                    ne.dist_params = (m * inflate, s * inflate)
                ne.annual_change_rate = cr
                sim.living_expense = ne
        sim.event_log.append(dict(
            year=sim.current_year, event="change_expense",
            detail=f"更改生活成本，新成本≈{sim.living_expense.base_value/1e4:.1f}W/年"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     new_expense=new_expense, raise_pct=raise_pct, raise_value=raise_value)

def change_invest_return(name="change_invest_return", trigger_year=2027,
                    new_return=None):
    """ Change living expenses, for example, due to miving to new locations """
    def _cb(sim, **kw):
        nr = kw["new_return"]
        sim.investment_return = nr
        sim.event_log.append(dict(
            year=sim.current_year, event="change_invest_return",
            detail=f"更改投资回报，新回报率≈{sim.investment_return.base_value*100:.1f}%"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     new_return=new_return)
