# -*- coding: utf-8 -*-
"""core/units.py - 数据字典（唯一注册表）与量纲换算（v4.1 阶段 3 第二步）

这个文件是**唯一**的序列事实来源：
  * 别名链（canonical id <- 各种历史叫法）
  * canonical 单位（决策④：TGA=百万美元，RRP=十亿美元）
  * 合理区间（量纲净化的判据）
  * SLA 与 severity（决策⑤ + 阶段 3 第一步分级）

`core/errors.py` 从本文件的 REGISTRY 派生策略，`core/data_proxy.py` 从本文件
派生别名/单位/区间——三处不再各写一份表。

本模块不抛异常、不碰数据库：只做纯数据与纯数学。
"""
from datetime import datetime

# ---------------------------------------------------------------- 单位常量
USD = 'usd'
MILLION_USD = 'million_usd'
BILLION_USD = 'billion_usd'
TRILLION_USD = 'trillion_usd'
PCT = '%'
BP = 'bp'
INDEX = 'index'
COUNT = 'count'

# 换算因子：value_in(from) * factor = value_in(to)
_CONVERSIONS = {
    ('trillion_usd', 'million_usd'): 1e6,
    ('trillion_usd', 'billion_usd'): 1e3,
    ('billion_usd', 'million_usd'): 1e3,
    ('million_usd', 'billion_usd'): 1e-3,
    ('million_usd', 'trillion_usd'): 1e-6,
    ('billion_usd', 'trillion_usd'): 1e-3,
    ('bp', '%'): 0.01,
    ('%', 'bp'): 100.0,
}


def conversion_factor(from_unit, to_unit):
    """返回 from -> to 的乘数；同单位返回 1.0；不可换算返回 None。"""
    if not from_unit or not to_unit:
        return None
    if from_unit == to_unit:
        return 1.0
    return _CONVERSIONS.get((from_unit, to_unit))


# ---------------------------------------------------------------- 注册表
# 每条：unit（canonical 单位）、range（canonical 单位下的合理闭区间）、
#       sla（天）、severity、freq、aliases（别名 -> 该别名自身的单位）
REGISTRY = {
    # ---- TGA：canonical = 百万美元（决策④）----
    'TGA_BALANCE': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 3,
        'severity': 'P0', 'freq': 'daily', 'aliases': {'TGA': MILLION_USD},
    },
    'TGA_DAILY': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 3,
        'severity': 'P0', 'freq': 'daily', 'aliases': {'TGA_DAILY_TREASURY': MILLION_USD},
    },
    'WTREGEN': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    # ---- RRP：canonical = 十亿美元（决策④）----
    'RRP_BALANCE': {
        'unit': BILLION_USD, 'range': (0.0, 5_000.0), 'sla': 2,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {'RRPONTSYD': BILLION_USD, 'ON_RRP': BILLION_USD},
    },
    'RRP_NYFED': {
        'unit': BILLION_USD, 'range': (0.0, 5_000.0), 'sla': 2,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    # ---- 利率：canonical = % ----
    'SOFR': {
        'unit': PCT, 'range': (-5.0, 30.0), 'sla': 2,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    'EFFR': {
        'unit': PCT, 'range': (-5.0, 30.0), 'sla': 2,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    # ---- 信用：决策⑥ 唯一 ID = HY_OAS，单位 % ----
    'HY_OAS': {
        'unit': PCT, 'range': (0.0, 40.0), 'sla': 3,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {
            'HY_SPREAD': PCT,           # FRED BAMLH0A0HYM2 落库名
            'BAMLH0A0HYM2': PCT,
            'US_HY_SPREAD': PCT,
        },
    },
    # ---- 利率曲线 ----
    'YC10Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
              'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'YC2Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
             'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'YC30Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
              'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'VIX': {'unit': INDEX, 'range': (0.0, 200.0), 'sla': 3,
            'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    # 美元指数：决策⑧ —— DXY 的唯一权威源是 market（ICE DXY ~99），
    # 历史上同一 series_id 里混进了 fred_csv 的广义美元指数（DTWEXBGS ~119），
    # 按 source_priority 只取 market；fred_csv 那批已迁移为独立的 BROAD_DOLLAR。
    'DXY_PROXY': {'unit': INDEX, 'range': (60.0, 200.0), 'sla': 3,
                  'severity': 'P1', 'freq': 'daily', 'aliases': {},
                  'source_priority': ('market',)},
    'BROAD_DOLLAR': {'unit': INDEX, 'range': (60.0, 200.0), 'sla': 8,
                     'severity': 'P2', 'freq': 'daily', 'aliases': {'DTWEXBGS': INDEX}},
    # ---- 美联储资产负债表 ----
    'FED_WALCL': {
        'unit': MILLION_USD, 'range': (0.0, 20_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    'FED_BALANCE_SHEET': {
        'unit': MILLION_USD, 'range': (0.0, 20_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    # ---- 参考性（P2）----
    'MICH_1Y_EXPECT': {'unit': PCT, 'range': (-2.0, 30.0), 'sla': 45,
                       'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
    'MICH_5Y_EXPECT': {'unit': PCT, 'range': (-2.0, 30.0), 'sla': 45,
                       'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
    # CPI / CPI_CORE 是**价格指数水平**（1982-84=100，当前约 313），不是百分比：
    # 引擎拿它算同比，若按 % 校验会被误判成量纲异常（回归测试抓到的真 bug）。
    'CPI_CORE': {'unit': INDEX, 'range': (0.0, 600.0), 'sla': 45,
                 'severity': 'P2', 'freq': 'monthly',
                 'aliases': {'CPILFESL': INDEX, 'CORE_CPI': INDEX}},
    'CPI': {'unit': INDEX, 'range': (0.0, 600.0), 'sla': 45,
            'severity': 'P2', 'freq': 'monthly', 'aliases': {'CPIAUCSL': INDEX}},
    'PPI': {'unit': INDEX, 'range': (0.0, 400.0), 'sla': 45,
            'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
    'PAYROLLS': {'unit': COUNT, 'range': (-5e6, 5e6), 'sla': 45,
                 'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
    'UNEMPLOYMENT': {'unit': PCT, 'range': (0.0, 40.0), 'sla': 45,
                     'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
}

DEFAULT_ENTRY = {
    'unit': None, 'range': None, 'sla': 8, 'severity': 'P2',
    'freq': 'unknown', 'aliases': {}, 'source_priority': (),
}

# 别名反查索引：任何叫法 -> canonical id
ALIAS_INDEX = {}
for _cid, _e in REGISTRY.items():
    ALIAS_INDEX[_cid.upper()] = _cid
    for _a in _e['aliases']:
        ALIAS_INDEX[_a.upper()] = _cid


def canonical_id(series_id):
    """把任意叫法归一成 canonical id；未登记则原样返回（去空格）。"""
    if not series_id:
        return series_id
    return ALIAS_INDEX.get(str(series_id).strip().upper(), str(series_id).strip())


def entry_of(series_id):
    """取注册表条目（按 canonical id）。未登记返回 DEFAULT_ENTRY 的副本。"""
    cid = canonical_id(series_id)
    e = REGISTRY.get(cid)
    if e is None:
        d = dict(DEFAULT_ENTRY)
        d['aliases'] = {}
        return cid, d
    return cid, e


def candidates_of(series_id):
    """候选序列顺序：canonical 自身 + 别名（按注册顺序）。"""
    cid, e = entry_of(series_id)
    return [cid] + list(e['aliases'].keys())


def unit_hint(series_id, used_id=None):
    """某个实际序列应当被当作什么单位：别名有声明就优先用它，否则用 canonical。"""
    cid, e = entry_of(series_id)
    if used_id and used_id in e['aliases']:
        return e['aliases'][used_id]
    return e.get('unit')


def to_canonical(value, series_id, from_unit=None):
    """把 value 从 from_unit 换算到 canonical 单位。

    返回 (canonical_value, factor, assumed)。无法换算时 factor=1、assumed=True
    （视为已经是 canonical），此时依靠区间校验兜底。
    """
    cid, e = entry_of(series_id)
    to_unit = e.get('unit')
    src = from_unit or to_unit
    if src == to_unit or to_unit is None:
        return float(value), 1.0, False
    f = conversion_factor(src, to_unit)
    if f is None:
        return float(value), 1.0, True     # 未知单位：按 canonical 处理，交给区间校验
    return float(value) * f, f, False


def in_range(value, series_id):
    """value（已换算到 canonical 单位）是否落在合理区间。未登记序列一律 True。"""
    cid, e = entry_of(series_id)
    rng = e.get('range')
    if not rng:
        return True
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    lo, hi = rng
    return lo <= v <= hi


def describe(series_id):
    cid, e = entry_of(series_id)
    return (f'{cid} unit={e.get("unit")} range={e.get("range")} '
            f'sla={e.get("sla")}d severity={e.get("severity")} '
            f'aliases={list(e.get("aliases", {}))}')


def days_lag(obs_date, asof=None):
    """自然日差（与 errors.days_between 同口径，放在这里避免 proxy 依赖 errors）。"""
    if not obs_date:
        return None
    asof = asof or datetime.now().strftime('%Y-%m-%d')
    a, b = _d(asof), _d(obs_date)
    return None if (a is None or b is None) else (a - b).days


def _d(s):
    s = str(s).strip()
    for fmt, n in (('%Y-%m-%d %H:%M:%S.%f', 26), ('%Y-%m-%d %H:%M:%S', 19),
                   ('%Y-%m-%dT%H:%M:%S', 19), ('%Y-%m-%d', 10), ('%Y%m%d', 8)):
        try:
            return datetime.strptime(s[:n], fmt).date()
        except ValueError:
            continue
    return None
