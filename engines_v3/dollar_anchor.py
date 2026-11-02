# -*- coding: utf-8 -*-
"""engines_v3/dollar_anchor.py - 美元锚定决策树（含 LIQUIDITY_SQUEEZE）"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=60):
    for col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {col} AS dt, value FROM observations "
                f"WHERE series_id=? ORDER BY {col} DESC LIMIT ?",
                conn, params=(sid, limit)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def _get_pct(conn, sid):
    try:
        df = pd.read_sql_query(
            "SELECT pct_5y FROM series_percentile WHERE series_id=? ORDER BY as_of_date DESC LIMIT 1",
            conn, params=(sid,)
        )
        if not df.empty and not pd.isna(df.iloc[0]['pct_5y']):
            return float(df.iloc[0]['pct_5y'])
    except Exception:
        pass
    return None


def compute_dollar_anchor(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        dxy = _load(conn, 'DXY_PROXY', 30)
        wti = _load(conn, 'WTI_OIL', 30)
        gold = _load(conn, 'GOLD_PRICE', 30)
        y10 = _load(conn, 'YC10Y', 30)
        silver = _load(conn, 'SILVER', 30)
        dxy_pct = _get_pct(conn, 'DXY_PROXY')
        gold_pct = _get_pct(conn, 'GOLD_PRICE')
        y10_pct = _get_pct(conn, 'US_10Y')
    finally:
        conn.close()

    result = {
        'asof': asof,
        'dxy': float(dxy.iloc[-1]) if len(dxy) >= 1 else None,
        'dxy_5y_pct': dxy_pct,
        'gold_5y_pct': gold_pct,
        'y10_5y_pct': y10_pct,
        'gsr': None,
        'assets': {}
    }

    def _chg_5d(s):
        if len(s) < 5:
            return 0.0
        return (float(s.iloc[-1]) - float(s.iloc[-5])) / float(s.iloc[-5]) * 100

    wti_chg = _chg_5d(wti)
    gold_chg = _chg_5d(gold)
    y10_chg = _chg_5d(y10)
    dxy_chg = _chg_5d(dxy)

    result['assets'] = {
        'WTI_5D': round(wti_chg, 2),
        'GOLD_5D': round(gold_chg, 2),
        'Y10_5D': round(y10_chg, 2),
        'DXY_5D': round(dxy_chg, 2)
    }

    if len(gold) >= 1 and len(silver) >= 1:
        try:
            gsr = float(gold.iloc[-1]) / float(silver.iloc[-1])
            result['gsr'] = round(gsr, 2)
        except Exception:
            pass

    # 美元状态
    if dxy_pct is not None and dxy_pct < 10:
        dollar_stance = 'STRUCTURALLY_WEAK'
        dollar_msg = f'💵 美元结构性走弱 (5y_pct={dxy_pct:.1f}%)'
    elif dxy_pct is not None and dxy_pct > 80:
        dollar_stance = 'STRUCTURALLY_STRONG'
        dollar_msg = f'💵 美元结构性强势 (5y_pct={dxy_pct:.1f}%)'
    else:
        dollar_stance = 'NEUTRAL'
        dollar_msg = f'💵 美元中性 (5y_pct={dxy_pct if dxy_pct else "N/A"})'

    # 四资产情景判定（含流动性挤压）
    if dxy_chg < 0 and wti_chg > 0 and gold_chg > 0 and y10_chg > 0:
        scenario = 'RATE_CUT_FORCED'
        scenario_msg = '🔴 降息倒逼路径（美元弱→油涨/金涨/债跌）'
    elif dxy_chg > 0 and wti_chg < 0 and gold_chg < 0 and y10_chg < 0:
        scenario = 'HIGH_RATE_MAINTAINED'
        scenario_msg = '🟢 高利率维持路径（美元强→油跌/金跌/债涨）'
    elif dxy_chg < 0 and wti_chg < 0 and gold_chg < 0 and y10_chg < 0:
        scenario = 'LIQUIDITY_SQUEEZE'
        scenario_msg = '🚨 流动性挤压（抛售一切换现金，上半场尾部特征）'
    else:
        scenario = 'MIXED'
        scenario_msg = '🟡 混合信号（四资产方向不一致）'

    result['dollar_stance'] = dollar_stance
    result['dollar_msg'] = dollar_msg
    result['scenario'] = scenario
    result['scenario_msg'] = scenario_msg

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS dollar_anchor (
        asof_date TEXT PRIMARY KEY, dxy REAL, dxy_5y_pct REAL,
        scenario TEXT, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO dollar_anchor
        (asof_date, dxy, dxy_5y_pct, scenario, detail) VALUES (?, ?, ?, ?, ?)""",
        (asof, result['dxy'], dxy_pct, scenario, json.dumps(result)))
    conn.commit()
    conn.close()

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_dollar_anchor(asof)
    print(f"\n{'='*60}")
    print(f"  美元锚定 - {asof}")
    print(f"{'='*60}")
    print(f"  {r['dollar_msg']}")
    print(f"  {r['scenario_msg']}")
    print(f"\n  四资产 5D 变化:")
    for k, v in r['assets'].items():
        print(f"    {k}: {v:+.2f}%")
    print(f"  金银比: {r['gsr']}")
    print(f"{'='*60}\n")