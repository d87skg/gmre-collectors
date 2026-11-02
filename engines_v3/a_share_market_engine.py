# -*- coding: utf-8 -*-
"""engines_v3/a_share_market_engine.py - A股市场底引擎"""
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


def compute_market_bottom(asof: str) -> dict:
    checks = {}
    score = 0

    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. 居民中长期信贷
        credit = _load(conn, 'CN_RESIDENT_LONG_LOAN', 6)
        if len(credit) >= 2:
            if credit.iloc[-1] > 0 and credit.iloc[-2] > 0:
                checks['credit'] = '✅ 连续 2 月正增长'
                score += 25
            else:
                checks['credit'] = '⚪ 未确认'
        else:
            checks['credit'] = 'N/A 数据缺失'

        # 2. 社融增速
        tsf = _load(conn, 'CN_TSF_YOY', 6)
        if len(tsf) >= 2:
            if tsf.iloc[-1] > tsf.iloc[-2]:
                checks['tsf'] = '✅ 社融增速回升'
                score += 20
            else:
                checks['tsf'] = '⚪ 未回升'
        else:
            checks['tsf'] = 'N/A 数据缺失'

        # 3. 北向资金
        northbound = _load(conn, 'CN_NORTHBOUND', 30)
        if len(northbound) >= 10:
            recent_10d_sum = float(northbound.tail(10).sum())
            if recent_10d_sum > 100:
                checks['northbound'] = f'✅ 10日净流入 {recent_10d_sum:.0f}亿'
                score += 15
            else:
                checks['northbound'] = f'⚪ 10日净流入 {recent_10d_sum:.0f}亿'
        else:
            checks['northbound'] = 'N/A 数据缺失'

        # 4. 30城地产销售（如果有）
        property_sales = _load(conn, 'CN_30CITY_PROPERTY_SALES', 8)
        if len(property_sales) >= 4:
            recent_4w = property_sales.tail(4)
            pct_chg = recent_4w.pct_change().dropna()
            if len(pct_chg) >= 3 and all(pct_chg > 0):
                checks['property'] = '✅ 连续 4 周改善'
                score += 30
            else:
                checks['property'] = '⚪ 未确认'
        else:
            checks['property'] = 'N/A 数据缺失'

        conn.close()
    except Exception as e:
        print(f"  ⚠️ A股市场底引擎异常: {e}")

    if score >= 60:
        level = 'MARKET_BOTTOM_CONFIRMED'
        action = '🟢 市场底确认，趋势行情条件成熟'
    elif score >= 40:
        level = 'MARKET_BOTTOM_FORMING'
        action = '🟡 市场底形成中'
    else:
        level = 'NOT_YET'
        action = '⚪ 市场底未确认，继续磨底'

    result = {
        'asof': asof,
        'score': score,
        'level': level,
        'checks': checks,
        'action': action,
        'note': '市场底必须基本面验证，不能只靠政策底'
    }

    try:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("""CREATE TABLE IF NOT EXISTS a_share_market (
            asof_date TEXT PRIMARY KEY, score REAL, level TEXT, detail TEXT)""")
        conn2.execute("""INSERT OR REPLACE INTO a_share_market
            (asof_date, score, level, detail) VALUES (?, ?, ?, ?)""",
            (asof, score, level, json.dumps(result)))
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_market_bottom(asof)
    print(f"\n{'='*60}")
    print(f"  A股市场底引擎 - {asof}")
    print(f"{'='*60}")
    print(f"  评分: {r['score']}/100 ({r['level']})")
    print(f"  检查: {r['checks']}")
    print(f"  动作: {r['action']}")
    print(f"{'='*60}\n")