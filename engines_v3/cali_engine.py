# -*- coding: utf-8 -*-
"""engines_v3/cali_engine.py - CALI 跨资产流动性指数"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=60):
    """加载序列，兼容 series_id='MOVE' 和 'MOVE_INDEX' 两种写法"""
    aliases = [sid]
    if sid == 'MOVE':
        aliases.append('MOVE_INDEX')
    for alias in aliases:
        for col in ['timestamp', 'date']:
            try:
                df = pd.read_sql_query(
                    f"SELECT {col} AS dt, value FROM observations "
                    f"WHERE series_id=? ORDER BY {col} DESC LIMIT ?",
                    conn, params=(alias, limit)
                )
                if not df.empty:
                    df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                    df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                    return df.sort_values('dt').set_index('dt')['value'].astype(float)
            except Exception:
                continue
    return pd.Series(dtype=float)


def compute_cali(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        move = _load(conn, 'MOVE', 30)
        vix = _load(conn, 'VIX', 30)
        hy = _load(conn, 'HY_SPREAD', 30)
        y10 = _load(conn, 'YC10Y', 30)
        y2 = _load(conn, 'YC2Y', 30)
    finally:
        conn.close()

    score = 0.0
    details = {}

    if len(move) >= 1:
        move_now = float(move.iloc[-1])
        move_vol = float(move.pct_change().tail(20).std()) if len(move) >= 20 else 0
        if move_now > 120:
            score += min((move_now - 120) * 0.5, 30)
        if move_vol > 0.05:
            score += 15
        details['MOVE'] = {'value': round(move_now, 1), 'vol': round(move_vol, 4)}
    else:
        details['MOVE'] = {'value': 'N/A'}

    if len(hy) >= 5:
        hy_slope = (float(hy.iloc[-1]) - float(hy.iloc[-5])) / 5
        if hy_slope > 0.01:
            score += min(hy_slope * 500, 25)
        details['HY_slope'] = round(hy_slope * 100, 2)
    else:
        details['HY_slope'] = 'N/A'

    if len(y10) >= 1 and len(y2) >= 1:
        term_premium = float(y10.iloc[-1]) - float(y2.iloc[-1])
        if term_premium > 0.30:
            score += min((term_premium - 0.30) * 100, 15)
        details['Term_Premium'] = round(term_premium * 100, 1)
    else:
        details['Term_Premium'] = 'N/A'

    if len(vix) >= 1:
        vix_now = float(vix.iloc[-1])
        if vix_now > 25:
            score += min((vix_now - 25), 15)
        details['VIX'] = round(vix_now, 2)
    else:
        details['VIX'] = 'N/A'

    score = min(score, 100)

    if score >= 70:
        level = 'CRITICAL'
        action = '🚨 流动性黑洞：清仓高Beta，保留现金'
    elif score >= 50:
        level = 'WARNING'
        action = '⚠️ 流动性紧张：减仓高杠杆，增配现金'
    elif score >= 30:
        level = 'CAUTION'
        action = '🟡 流动性趋紧：监控，准备防守'
    else:
        level = 'NORMAL'
        action = '🟢 流动性正常：维持当前配置'

    result = {
        'asof': asof,
        'cali_score': round(score, 1),
        'level': level,
        'action': action,
        'details': details
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS cali_engine (
        asof_date TEXT PRIMARY KEY, cali_score REAL, level TEXT, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO cali_engine
        (asof_date, cali_score, level, detail) VALUES (?, ?, ?, ?)""",
        (asof, score, level, json.dumps(details)))
    conn.commit()
    conn.close()

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_cali(asof)
    print(f"\n{'='*60}")
    print(f"  CALI 跨资产流动性 - {asof}")
    print(f"{'='*60}")
    print(f"  评分: {r['cali_score']}/100 ({r['level']})")
    print(f"  建议: {r['action']}")
    print(f"  详情: {r['details']}")
    print(f"{'='*60}\n")