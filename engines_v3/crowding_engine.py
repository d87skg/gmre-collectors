# -*- coding: utf-8 -*-
"""engines_v3/crowding_engine.py - 拥挤度引擎（CFTC + ETF + Deribit PCR）"""
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


def compute_crowding(asof: str) -> dict:
    score = 0.0
    details = {}

    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. CFTC COT - 日元空头历史分位
        try:
            df = pd.read_sql_query(
                "SELECT net_noncommercial FROM cftc_fx WHERE series_id='COT_JPY' ORDER BY date DESC LIMIT 260",
                conn
            )
            if not df.empty and len(df) >= 20:
                vals = df['net_noncommercial'].astype(float)
                current = float(vals.iloc[0])
                pct = (vals > current).mean() * 100  # 空头越多，反向分位越高
                if pct > 90:
                    score += 40
                elif pct > 80:
                    score += 25
                details['JPY_COT_pct'] = round(pct, 1)
            else:
                details['JPY_COT_pct'] = 'N/A'
        except Exception as e:
            details['JPY_COT_pct'] = f'ERR:{str(e)[:20]}'

        # 2. BTC 资金费率历史分位
        try:
            df = pd.read_sql_query(
                "SELECT value FROM observations WHERE series_id='BTC_FUNDING_RATE_1H' ORDER BY timestamp DESC LIMIT 500",
                conn
            )
            if not df.empty and len(df) >= 20:
                vals = df['value'].astype(float)
                current = float(vals.iloc[0])
                pct = (vals < current).mean() * 100
                if pct > 95:
                    score += 30
                elif pct > 85:
                    score += 15
                details['BTC_FR_pct'] = round(pct, 1)
            else:
                details['BTC_FR_pct'] = 'N/A'
        except Exception as e:
            details['BTC_FR_pct'] = f'ERR:{str(e)[:20]}'

        # 3. Deribit PCR
        try:
            df = pd.read_sql_query(
                "SELECT pcr FROM deribit_skew ORDER BY rowid DESC LIMIT 1", conn
            )
            if not df.empty and pd.notna(df.iloc[0]['pcr']):
                pcr = float(df.iloc[0]['pcr'])
                if pcr > 1.2:
                    score += 20
                elif pcr > 0.9:
                    score += 10
                details['PCR'] = round(pcr, 3)
            else:
                details['PCR'] = 'N/A'
        except Exception as e:
            details['PCR'] = f'ERR:{str(e)[:20]}'

        # 4. 美股 ETF 资金流（TLT 流出 + GLD 流入 = 拥挤切换）
        try:
            tlt = _get_pct(conn, 'TLT_VOLUME')
            gld = _get_pct(conn, 'GLD_VOLUME')
            details['TLT_vol_pct'] = tlt
            details['GLD_vol_pct'] = gld
            if tlt is not None and gld is not None:
                if tlt > 80 and gld > 80:
                    score += 10
        except Exception as e:
            details['ETF_flow'] = f'ERR:{str(e)[:20]}'

        conn.close()
    except Exception as e:
        print(f"  ⚠️ Crowding 引擎异常: {e}")

    score = min(score, 100)

    if score >= 70:
        level = 'EXTREME'
        action = '🚨 拥挤度极端：警惕踩踏式去杠杆'
    elif score >= 50:
        level = 'HIGH'
        action = '⚠️ 拥挤度高：多头/空头任一方向过度拥挤'
    elif score >= 30:
        level = 'MEDIUM'
        action = '🟡 拥挤度中等：常规监控'
    else:
        level = 'LOW'
        action = '🟢 拥挤度低：筹码分布正常'

    result = {
        'asof': asof,
        'score': round(score, 1),
        'level': level,
        'action': action,
        'details': details
    }

    try:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("""CREATE TABLE IF NOT EXISTS crowding_engine (
            asof_date TEXT PRIMARY KEY, score REAL, level TEXT, detail TEXT)""")
        conn2.execute("""INSERT OR REPLACE INTO crowding_engine
            (asof_date, score, level, detail) VALUES (?, ?, ?, ?)""",
            (asof, score, level, json.dumps(details)))
        conn2.commit()
        conn2.close()
    except Exception as e:
        print(f"  ⚠️ Crowding 落盘失败: {e}")

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_crowding(asof)
    print(f"\n{'='*60}")
    print(f"  拥挤度引擎 - {asof}")
    print(f"{'='*60}")
    print(f"  评分: {r['score']}/100 ({r['level']})")
    print(f"  建议: {r['action']}")
    print(f"  详情: {r['details']}")
    print(f"{'='*60}\n")