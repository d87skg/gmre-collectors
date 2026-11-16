# -*- coding: utf-8 -*-
"""core/units.py - 数据字典（唯一注册表）与量纲换算（v4.2: 多源冗余版）"""
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
    if not from_unit or not to_unit:
        return None
    if from_unit == to_unit:
        return 1.0
    return _CONVERSIONS.get((from_unit, to_unit))


# ---------------------------------------------------------------- 注册表
# 注意：aliases 是有序的——data_proxy 会按顺序尝试，选择"最新"的一个。
REGISTRY = {
    'TGA_BALANCE': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 5,
        'severity': 'P0', 'freq': 'daily', 'aliases': {'TGA': MILLION_USD},
    },
    'TGA_DAILY': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 5,
        'severity': 'P0', 'freq': 'daily', 'aliases': {'TGA_DAILY_TREASURY': MILLION_USD},
    },
    'WTREGEN': {
        'unit': MILLION_USD, 'range': (0.0, 5_000_000.0), 'sla': 45,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    'RRP_BALANCE': {
        'unit': BILLION_USD, 'range': (0.0, 5_000.0), 'sla': 5,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {'RRPONTSYD': BILLION_USD, 'ON_RRP': BILLION_USD},
    },
    'RRP_NYFED': {
        'unit': BILLION_USD, 'range': (0.0, 5_000.0), 'sla': 5,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    # ---- 利率：主源 FRED，备源 BIS（日频）----
    'SOFR': {
        'unit': PCT, 'range': (-5.0, 30.0), 'sla': 5,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    'EFFR': {
        'unit': PCT, 'range': (-5.0, 30.0), 'sla': 5,
        'severity': 'P0', 'freq': 'daily', 'aliases': {},
    },
    'FEDFUNDS': {
        'unit': PCT, 'range': (-5.0, 30.0), 'sla': 45,
        'severity': 'P1', 'freq': 'monthly',
        'aliases': {
            'FEDFUNDS_BIS': PCT,        # BIS 日频央行利率
            'FEDFUNDS_ECONDASH': PCT,   # 备用（暂未启用）
        },
    },
    'HY_OAS': {
        'unit': PCT, 'range': (0.0, 40.0), 'sla': 3,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {
            'HY_SPREAD': PCT, 'BAMLH0A0HYM2': PCT, 'US_HY_SPREAD': PCT,
        },
    },
    'YC10Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
              'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'YC2Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
             'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'YC30Y': {'unit': PCT, 'range': (-5.0, 30.0), 'sla': 3,
              'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    'VIX': {'unit': INDEX, 'range': (0.0, 200.0), 'sla': 3,
            'severity': 'P1', 'freq': 'daily', 'aliases': {}},
    # ---- 美元指数：主源 market，备源 BIS ----
    'DXY_PROXY': {
        'unit': INDEX, 'range': (60.0, 200.0), 'sla': 7,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {'DXY_PROXY_BIS': INDEX},
    },
    'BROAD_DOLLAR': {'unit': INDEX, 'range': (60.0, 200.0), 'sla': 45,
                     'severity': 'P1', 'freq': 'daily', 'aliases': {'DTWEXBGS': INDEX}},
    'FED_WALCL': {
        'unit': MILLION_USD, 'range': (0.0, 20_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    'FED_BALANCE_SHEET': {
        'unit': MILLION_USD, 'range': (0.0, 20_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'weekly', 'aliases': {},
    },
    # ---- 商品：主源 FRED/Yahoo，备源 Twelve Data ----
    'WTI_OIL': {
        'unit': USD, 'range': (0.0, 500.0), 'sla': 8,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {'WTI_OIL_TD': USD},
    },
    'GOLD_PRICE': {
        'unit': USD, 'range': (0.0, 20_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'daily',
        'aliases': {'GOLD_PRICE_TD': USD},
    },
    # ---- 加密：主源交易所，备源 CoinGecko ----
    'BTC_SPOT_PRICE_1H': {
        'unit': USD, 'range': (0.0, 1_000_000.0), 'sla': 8,
        'severity': 'P1', 'freq': 'hourly',
        'aliases': {'BTC_SPOT_PRICE_1H_CG': USD},
    },
    'ETH_PRICE': {
        'unit': USD, 'range': (0.0, 100_000.0), 'sla': 8,
        'severity': 'P2', 'freq': 'daily',
        'aliases': {'ETH_PRICE_CG': USD},
    },
    # ---- 参考性（P2）----
    'MICH_1Y_EXPECT': {'unit': PCT, 'range': (-2.0, 30.0), 'sla': 45,
                       'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
    'MICH_5Y_EXPECT': {'unit': PCT, 'range': (-2.0, 30.0), 'sla': 45,
                       'severity': 'P2', 'freq': 'monthly', 'aliases': {}},
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

ALIAS_INDEX = {}
for _cid, _e in REGISTRY.items():
    ALIAS_INDEX[_cid.upper()] = _cid
    for _a in _e['aliases']:
        ALIAS_INDEX[_a.upper()] = _cid


def canonical_id(series_id):
    if not series_id:
        return series_id
    return ALIAS_INDEX.get(str(series_id).strip().upper(), str(series_id).strip())


def entry_of(series_id):
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
    cid, e = entry_of(series_id)
    if used_id and used_id in e['aliases']:
        return e['aliases'][used_id]
    return e.get('unit')


def to_canonical(value, series_id, from_unit=None):
    cid, e = entry_of(series_id)
    to_unit = e.get('unit')
    src = from_unit or to_unit
    if src == to_unit or to_unit is None:
        return float(value), 1.0, False
    f = conversion_factor(src, to_unit)
    if f is None:
        return float(value), 1.0, True
    return float(value) * f, f, False


def in_range(value, series_id):
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