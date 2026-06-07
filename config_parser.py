"""
config_parser.py - 财务人生模拟器配置文件解析器
==========================================================

配置文件格式说明
----------------
1. 以 # 开头的行为注释，空行被忽略
2. [section] 定义段落，支持的段落：
   - [simulation]       模拟参数
   - [initial_assets]   初始资产
   - [initial_house]    初始房产（含按揭贷款），可选
   - [initial_car]      初始车产（含车贷），可选
   - [salary]           工资参数
   - [living_expense]   生活费参数
   - [investment_return] 投资回报率参数
   - [inflation_rate]   通胀率参数
   - [events]           人生事件列表

3. 参数值格式：
   - 固定值:        100_000
   - 正态分布:      100_000 ~ N(100_000, 10_000)
   - 均匀分布:      100_000 ~ U(80_000, 120_000)
   
4. 百分比支持:
   - 0.049  或  4.9%  均可，% 会自动转换为小数

5. 事件格式（[events] 段落中每行一个事件）：
   事件类型 | 触发年份 | 参数1=值1 | 参数2=值2 | ...
   触发年份也可以写 auto，表示从 start_year+1 到 end_year 每年触发

6. 支持的事件类型及参数：
   - buy_house  : house_price, down_pct, mortgage_years, mortgage_rate, appreciation
   - buy_car    : car_price, down_pct, loan_years, loan_rate
   - job_change : new_salary（按当前购买力，自动通胀换算）, raise_pct, raise_value（按当前购买力）
   - marriage   : partner_income（按当前购买力，自动通胀换算）, extra_expense（按当前购买力，自动通胀换算）
   - birth      : child_cost（按当前购买力，自动通胀换算）, edu_start_age, edu_cost（按当前购买力，自动通胀换算）
   - retirement : (无额外参数)
   - redistribute_invest : (无额外参数)
   - change_living_expense : new_expense（按当前购买力，自动通胀换算）, raise_pct, raise_value（按当前购买力）
   - change_invest_return : new_return
"""

import re
from lifeclass import Parameter, FinanceLifeSim
from events_factory import *


# ──────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────

def _parse_percent(s):
    """将 '3%' → 0.03, '4.9%' → 0.049, '0.03' → 0.03"""
    s = s.strip()
    if s.endswith('%'):
        return float(s[:-1].replace('_', '')) / 100.0
    return float(s.replace('_', ''))


def _parse_simple_value(s):
    """解析简单数值（支持百分比和下划线分隔）"""
    s = s.strip()
    if s.endswith('%'):
        return float(s[:-1].replace('_', '')) / 100.0
    return float(s.replace('_', ''))


def _parse_param_value(s):
    """
    解析 Parameter 参数值，返回 dict:
      {"value": float, "dist_type": str, "dist_params": tuple|None, "annual_change_rate": float}

    格式示例:
      100_000                                    → fixed
      100_000 ~ N(100_000, 10_000)              → normal
      6% ~ N(6%, 15%)                           → normal (百分比)
      100_000 ~ U(80_000, 120_000)              → uniform
                """
    s = s.strip()
    tilde_idx = s.find('~')
    if tilde_idx == -1:
        return {"value": _parse_simple_value(s), "dist_type": "fixed",
                "dist_params": None, "annual_change_rate": 0.0}

    value_part = s[:tilde_idx].strip()
    dist_part = s[tilde_idx + 1:].strip()
    base_value = _parse_simple_value(value_part)

    m = re.match(r'(\w+)\((.+)\)', dist_part)
    if not m:
        raise ValueError(f"无法解析分布: {dist_part}")

    dist_name = m.group(1).upper()
    params_str = m.group(2)
    raw_params = [p.strip() for p in params_str.split(',')]

    # 如果基准值用了百分比写法，分布参数也按百分比解析
    is_pct = value_part.strip().endswith('%')
    if is_pct:
        dist_params = tuple(_parse_percent(p) for p in raw_params)
    else:
        dist_params = tuple(float(p.replace('_', '')) for p in raw_params)

    dist_type_map = {'N': 'normal', 'U': 'uniform'}
    dist_type = dist_type_map.get(dist_name)
    if dist_type is None:
        raise ValueError(f"未知分布类型: {dist_name}，支持: N, U")

    return {"value": base_value, "dist_type": dist_type,
            "dist_params": dist_params, "annual_change_rate": 0.0}


def _build_parameter(param_dict):
    """从 _parse_param_value 返回的 dict 构建 Parameter 对象"""
    d = param_dict
    return Parameter(
        value=d["value"], dist_type=d["dist_type"],
        dist_params=d["dist_params"], annual_change_rate=d["annual_change_rate"],
    )


# ──────────────────────────────────────────
# 配置文件解析
# ──────────────────────────────────────────

def _parse_key_value_section(lines):
    """解析 key = value 段落"""
    d = {}
    for line in lines:
        if '=' in line:
            key, val = line.split('=', 1)
            key = key.strip(); val = val.strip()
            try:
                d[key] = _parse_simple_value(val)
            except ValueError:
                d[key] = val
    return d


def _parse_param_section(lines):
    """解析参数段落（含 value 和 annual_change_rate）"""
    d = {"value": 0, "dist_type": "fixed", "dist_params": None, "annual_change_rate": 0.0}
    for line in lines:
        if '=' not in line:
            continue
        key, val = line.split('=', 1)
        key = key.strip(); val = val.strip()
        if key == 'value':
            d.update(_parse_param_value(val))
        elif key == 'annual_change_rate':
            d['annual_change_rate'] = _parse_percent(val)
        else:
            raise ValueError(f"参数段落中不支持的字段: {key}")
    return d


def _parse_events_section(lines):
    """解析事件段落，返回 list of (event_type, trigger_year, kwargs)"""
    events = []
    for line in lines:
        if line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        event_type = parts[0]
        trigger_year_str = parts[1]
        kwargs = {}
        for p in parts[2:]:
            if '=' not in p:
                continue
            k, v = p.split('=', 1)
            k = k.strip(); v = v.strip()
            try:
                kwargs[k] = _parse_simple_value(v)
            except ValueError:
                if '~' in v:
                    kwargs[k] = _build_parameter(_parse_param_value(v))
                else:
                    kwargs[k] = v
        if trigger_year_str.lower() == 'auto':
            trigger_year = 'auto'
        else:
            trigger_year = int(trigger_year_str.replace('_', ''))
        events.append((event_type, trigger_year, kwargs))
    return events


def parse_config(filepath):
    """
    解析配置文件，返回一个 dict，包含:
      - simulation: {start_year, end_year, n_samples, seed}
      - initial_assets: {cash, investments, real_estate, other_assets, liabilities}
      - salary / living_expense / investment_return / inflation_rate: Parameter
      - events: list of (event_type, trigger_year_or_auto, kwargs)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    sections = {}
    current_section = None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        sec_match = re.match(r'\[(\w+)\]', stripped)
        if sec_match:
            current_section = sec_match.group(1)
            if current_section not in sections:
                sections[current_section] = []
            continue
        if current_section is not None:
            sections[current_section].append(stripped)

    result = {}
    result['simulation'] = _parse_key_value_section(sections.get('simulation', []))
    result['initial_assets'] = _parse_key_value_section(sections.get('initial_assets', []))
    result['initial_house'] = _parse_key_value_section(sections.get('initial_house', []))
    result['initial_car'] = _parse_key_value_section(sections.get('initial_car', []))

    for param_name in ['salary', 'living_expense', 'investment_return', 'inflation_rate']:
        section_lines = sections.get(param_name, [])
        param_dict = _parse_param_section(section_lines)
        result[param_name] = _build_parameter(param_dict)

    result['events'] = _parse_events_section(sections.get('events', []))
    return result


# ──────────────────────────────────────────
# 从配置创建模拟器
# ──────────────────────────────────────────

EVENT_FACTORIES = {
    'buy_house': make_buy_house,
    'buy_car': make_buy_car,
    'job_change': make_job_change,
    'marriage': make_marriage,
    'birth': make_birth,
    'retirement': make_retirement,
    'redistribute_invest': make_redistribute_invest,
    'change_living_expense': change_living_expense,
    'change_invest_return': change_invest_return,
}


def create_sim_from_config(config):
    """从解析后的配置 dict 创建 FinanceLifeSim 实例"""
    sim_cfg = config['simulation']
    assets_cfg = config['initial_assets']
    start_year = int(sim_cfg.get('start_year', 2024))

    sim = FinanceLifeSim(
        init_cash=assets_cfg.get('cash', 0),
        init_investments=assets_cfg.get('investments', 0),
        init_real_estate=0,
        init_other_assets=0,
        init_liabilities=0,
        salary=config['salary'],
        living_expense=config['living_expense'],
        investment_return=config['investment_return'],
        inflation_rate=config['inflation_rate'],
        start_year=start_year,
    )

    # --- 初始房产（含按揭贷款）---
    house_cfg = config.get('initial_house', {})
    if house_cfg.get('value', 0) > 0:
        sim.real_estate = house_cfg['value']
        sim.house_appreciation_rate = house_cfg.get('appreciation', 0.0)
        rem_mortgage = house_cfg.get('remaining_mortgage', 0)
        if rem_mortgage > 0:
            sim.liabilities += rem_mortgage
            sim.mortgages.append({
                'remaining': rem_mortgage,
                'annual_rate': house_cfg.get('mortgage_rate', 0.035),
                'total_years': house_cfg.get('remaining_years', 30),
                'start_year': sim.current_year,
            })

    # --- 初始车产（含车贷）---
    car_cfg = config.get('initial_car', {})
    if car_cfg.get('value', 0) > 0:
        sim.other_assets += car_cfg['value']
        rem_loan = car_cfg.get('remaining_loan', 0)
        if rem_loan > 0:
            sim.liabilities += rem_loan
            sim.car_loans.append({
                'remaining': rem_loan,
                'annual_rate': car_cfg.get('loan_rate', 0.03),
                'total_years': car_cfg.get('remaining_years', 3),
                'start_year': sim.current_year,
            })

    end_year = int(sim_cfg.get('end_year', 2060))
    for event_type, trigger_year, kwargs in config['events']:
        factory = EVENT_FACTORIES.get(event_type)
        if factory is None:
            print(f"警告: 未知事件类型 '{event_type}'，已跳过")
            continue
        if trigger_year == 'auto':
            for yr in range(start_year + 1, end_year + 1):
                evt = factory(name=f"{event_type}_{yr}", trigger_year=yr, **kwargs)
                sim.add_event(evt)
        else:
            evt = factory(name=event_type, trigger_year=trigger_year, **kwargs)
            sim.add_event(evt)

    return sim


def get_sim_config(config):
    """从配置 dict 中提取模拟运行参数"""
    sim_cfg = config['simulation']
    return {
        'end_year': int(sim_cfg.get('end_year', 2060)),
        'n_samples': int(sim_cfg.get('n_samples', 1000)),
        'seed': int(sim_cfg.get('seed', 42)),
        'inflation_adjusted': sim_cfg.get('inflation_adjusted', 'true'),
    }
