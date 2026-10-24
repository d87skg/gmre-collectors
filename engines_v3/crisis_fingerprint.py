"""engines_v3/crisis_fingerprint.py - VS5: 历史危机指纹比对"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'

# 8个核心历史危机（起点日期 + 机制标签）
CRISES = {
    '1987_BlackMonday': {
        'date': '1987-10-19',
        'mechanism': '估值崩溃 + 组合保险触发',
        'signature': {'rates': -0.3, 'credit': 0.2, 'liquidity': 0.3, 'equity': 0.5, 'vix': 0.9}
    },
    '1998_LTCM': {
        'date': '1998-08-17',
        'mechanism': '杠杆清算 + 流动性冲击',
        'signature': {'rates': -0.5, 'credit': 0.6, 'liquidity': 0.7, 'equity': 0.4, 'vix': 0.8}
    },
    '2008_GFC': {
        'date': '2008-09-15',
        'mechanism': '信用崩塌 + 银行破产 + 系统性去杠杆',
        'signature': {'rates': -0.8, 'credit': 1.0, 'liquidity': 0.9, 'equity': 0.9, 'vix': 1.0}
    },
    '2011_EuroCrisis': {
        'date': '2011-08-05',
        'mechanism': '主权债务危机 + 信用传染',
        'signature': {'rates': -0.4, 'credit': 0.7, 'liquidity': 0.4, 'equity': 0.5, 'vix': 0.7}
    },
    '2015_ChinaDeval': {
        'date': '2015-08-11',
        'mechanism': '汇率冲击 + 新兴市场传染',
        'signature': {'rates': -0.2, 'credit': 0.4, 'liquidity': 0.5, 'equity': 0.6, 'vix': 0.6}
    },
    '2018_Volmageddon': {
        'date': '2018-02-05',
        'mechanism': '波动率冲击 + 做空VIX清算',
        'signature': {'rates': 0.1, 'credit': 0.2, 'liquidity': 0.3, 'equity': 0.4, 'vix': 1.0}
    },
    '2020_COVID': {
        'date': '2020-03-16',
        'mechanism': '外生冲击 + 流动性冻结 + 政策干预',
        'signature': {'rates': -0.7, 'credit': 0.8, 'liquidity': 1.0, 'equity': 0.9, 'vix': 1.0}
    },
    '2022_RatesShock': {
        'date': '2022-06-13',
        'mechanism': '通胀冲击 + 政策重定价 + 估值压缩',
        'signature': {'rates': 1.0, 'credit': 0.5, 'liquidity': 0.4, 'equity': 0.6, 'vix': 0.6}
    },
    '2024_YenCarry': {
        'date': '2024-08-05',
        'mechanism': '日元套利清算 + 跨资产去杠杆',
        'signature': {'rates': -0.2, 'credit': 0.4, 'liquidity': 0.5, 'equity': 0.5, 'vix': 0.9}
    },
}


def _normalize(v, lo, hi):
    return float(np.clip((v - lo) / (hi - lo), 0, 1))


def _current_signature(conn):
    """从当前系统状态构建签名向量"""
    sig = {}

    # Rates: 10Y变化方向
    try:
        y10 = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id='YC10Y' ORDER BY timestamp DESC LIMIT 30",
            conn
        )['value'].astype(float)
        if len(y10) >= 20:
            chg = (y10.iloc[0] - y10.iloc[-1])
            sig['rates'] = _normalize(chg, -0.5, 0.5)
        else:
            sig['rates'] = 0.5
    except Exception:
        sig['rates'] = 0.5

    # Credit: HY利差20日变化
    try:
        hyg = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id='HY_SPREAD' ORDER BY timestamp DESC LIMIT 30",
            conn
        )['value'].astype(float)
        if len(hyg) >= 20:
            chg = (hyg.iloc[0] - hyg.iloc[-1])
            sig['credit'] = _normalize(chg, -2, 3)
        else:
            sig['credit'] = 0.5
    except Exception:
        sig['credit'] = 0.5

    # Liquidity: RRP耗尽度
    try:
        rrp = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id='RRP_BALANCE' ORDER BY timestamp DESC LIMIT 1",
            conn
        )['value'].astype(float)
        if len(rrp) >= 1:
            sig['liquidity'] = _normalize(500 - float(rrp.iloc[0]), 0, 500)
        else:
            sig['liquidity'] = 0.5
    except Exception:
        sig['liquidity'] = 0.5

    # Equity: SP500 20日回撤
    try:
        spx = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id='SP500' ORDER BY timestamp DESC LIMIT 30",
            conn
        )['value'].astype(float)
        if len(spx) >= 20:
            peak = spx.max()
            now = spx.iloc[0]
            dd = (peak - now) / peak
            sig['equity'] = _normalize(dd, 0, 0.20)
        else:
            sig['equity'] = 0.5
    except Exception:
        sig['equity'] = 0.5

    # VIX: 绝对水平
    try:
        vix = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id='VIX' ORDER BY timestamp DESC LIMIT 1",
            conn
        )['value'].astype(float)
        if len(vix) >= 1:
            sig['vix'] = _normalize(float(vix.iloc[0]), 15, 60)
        else:
            sig['vix'] = 0.5
    except Exception:
        sig['vix'] = 0.5

    return sig


def _similarity(current, template):
    """余弦相似度"""
    keys = list(current.keys())
    a = np.array([current[k] for k in keys])
    b = np.array([template[k] for k in keys])
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_fingerprint(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        current = _current_signature(conn)
    finally:
        conn.close()

    results = []
    for name, crisis in CRISES.items():
        sim = _similarity(current, crisis['signature'])
        results.append({
            'crisis': name,
            'date': crisis['date'],
            'mechanism': crisis['mechanism'],
            'similarity': round(sim, 3)
        })

    results_sorted = sorted(results, key=lambda x: x['similarity'], reverse=True)

    output = {
        'asof': asof,
        'current_signature': current,
        'matches': results_sorted
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS crisis_fingerprint (
        asof_date TEXT PRIMARY KEY, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO crisis_fingerprint
        (asof_date, detail) VALUES (?, ?)""",
        (asof, json.dumps(results_sorted)))
    conn.commit()
    conn.close()

    # 打印
    print(f"\n{'='*70}")
    print(f"  Crisis Fingerprint - {asof}")
    print(f"{'='*70}\n")
    print(f"  当前签名向量:")
    for k, v in current.items():
        print(f"    {k:12s} = {v:.3f}")
    print(f"\n  历史相似度排名（Top 5）:")
    for i, r in enumerate(results_sorted[:5], 1):
        bar = '#' * int(r['similarity'] * 30)
        print(f"    {i}. {r['crisis']:22s} {r['similarity']:.3f} {bar}")
        print(f"       机制: {r['mechanism']}")
    print(f"\n  ⚠️ 相似 ≠ 预测。这只是结构相似度，不是未来结果。")
    print(f"{'='*70}\n")

    return output


if __name__ == "__main__":
    compute_fingerprint(datetime.now().strftime('%Y-%m-%d'))