from lifeclass import *
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
    """跳槽 / 涨薪"""
    def _cb(sim, **kw):
        ns = kw["new_salary"]
        rp = kw["raise_pct"]
        rv = kw["raise_value"]
        if rp is not None:
            new_value = sim.salary.base_value * (1+rp)
            sim.salary.change_value(new_value)
        elif rv is not None:
            sim.salary.change_value(sim.salary.base_value + rv)
        else:
            cr = sim.salary.annual_change_rate
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
    """结婚：增加配偶收入 + 共同支出"""
    def _cb(sim, **kw):
        sim.salary.base_value += kw["partner_income"]
        if sim.salary.dist_type == "normal":
            m, s = sim.salary.dist_params
            sim.salary.dist_params = (m + kw["partner_income"], s * (1 + kw["partner_income"]/m))
        sim.living_expense.base_value += kw["extra_expense"]
        sim.event_log.append(dict(
            year=sim.current_year, event="marriage",
            detail=f"结婚  家庭收入+{kw['partner_income']/1e4:.0f}W  "
                   f"支出+{kw['extra_expense']/1e4:.1f}W"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     partner_income=partner_income,
                     extra_expense=extra_expense)


def make_birth(name="birth", trigger_year=2027,
               child_cost=30_000, edu_start_age=6,
               edu_cost=50_000):
    """生子"""
    def _cb(sim, **kw):
        sim.child_count += 1
        sim.living_expense.change_value(sim.living_expense.base_value+kw["child_cost"])
        sim.children.append(dict(
            birth_year=sim.current_year,
            edu_start_age=kw["edu_start_age"],
            edu_cost=kw["edu_cost"],
        ))
        sim.event_log.append(dict(
            year=sim.current_year, event="birth",
            detail=f"生子  年支出+{kw['child_cost']/1e4:.1f}W"
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
    """ Change living expenses, for example, due to miving to new locations """
    def _cb(sim, **kw):
        ne = kw["new_expense"]
        rp = kw["raise_pct"]
        rv = kw["raise_value"]
        if rp is not None:
            new_value = sim.living_expense.base_value * (1+rp)
            sim.living_expense.change_value(new_value)
        elif rv is not None:
            sim.living_expense.change_value(sim.living_expense.base_value + rv)
        else:
            cr = sim.living_expense.annual_change_rate
            ne.annual_change_rate = cr
            sim.living_expense = ne
        sim.event_log.append(dict(
            year=sim.current_year, event="job_change",
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
            year=sim.current_year, event="job_change",
            detail=f"更改投资回报，新回报率≈{sim.investment_return.base_value*100:.1f}%"
        ))
    return LifeEvent(name, trigger_year=trigger_year,
                     callback=_cb,
                     new_return=new_return)
