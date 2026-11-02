# -*- coding: utf-8 -*-
"""engines_v3/crowding_engine.py - 拥挤度引擎（v4: CSV 优先 + SQLite 兜底）"""
import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = 'data/macro.db'


def _table_exists(conn, table):
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _get_columns(conn, table):
    try:
        df = pd.read_sql_query(f"PRAGMA table_info({table})", conn)
        return [r['name'] for _, r in df.iterrows()]
    except Exception:
        return []


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
    try:
        df_obs = pd.read_sql_query(
            "SELECT value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1260",
            conn, params=(sid,)
        )
        if len(df_obs) >= 20:
            vals = df_obs['value'].astype(float)
            current = float(vals.iloc[0])
            return round((vals < current).mean() * 100, 2)
    except Exception:
        pass
    return None


def _query_jpy_cot_csv():
    """从 cftc_fx.csv 读取日元空头分位"""
    p = Path('data/cftc_fx.csv')
    if not p.exists():
        return None, 'no_csv'
    try:
        df = pd.read_csv(p)
        if 'net_noncommercial' not in df.columns or 'series_id' not in df.columns:
            return None, f'no_col({list(df.columns)[:5]})'
        # 尝试多种 series_id
        for sid in ['COT_JPY', 'JPY', 'COT_JAPANESE_YEN', 'JAPANESE YEN']:
            sub = df[df['series_id'] == sid].sort_values('date', ascending=False).head(260)
            if len(sub) >= 20:
                vals = sub['net_noncommercial'].astype(float)
                current = float(vals.iloc[0])
                pct = (vals > current).mean() * 100
                return round(pct, 1), f'ok_csv({sid})'
        return None, 'no_series_id'
    except Exception as e:
        return None, f'err_csv({str(e)[:20]})'


def _query_pcr_csv():
    """从 deribit_skew.csv 读取 PCR"""
    p = Path('data/deribit_skew.csv')
    if not p.exists():
        return None, 'no_csv'
    try:
        df = pd.read_csv(p)
        for col in ['pcr', 'pcr_25d', 'put_call_ratio']:
            if col in df.columns and not df.empty and pd.notna(df.iloc[-1][col]):
                return float(df.iloc[-1][col]), f'ok_csv({col})'
        return None, 'no_pcr_col'
    except Exception as e:
        return None, f'err_csv({str(e)[:20]})'


def compute_crowding(asof: str) -> dict:
    score = 0.0
    details = {}
    diag = {}

    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. CFTC 日元空头：SQLite 优先，CSV 兜底
        jpy_pct, jpy_diag = None, None
        if _table_exists(conn, 'cftc_fx') and 'net_noncommercial' in _get_columns(conn, 'cftc_fx'):
            try:
                for sid in ['COT_JPY', 'JPY']:
                    df = pd.read_sql_query(
                        "SELECT net_noncommercial FROM cftc_fx WHERE series_id=? ORDER BY date DESC LIMIT 260",
                        conn, params=(sid,)
                    )
                    if len(df) >= 20:
                        vals = df['net_noncommercial'].astype(float)
                        jpy_pct = round((vals > float(vals.iloc[0])).mean() * 100, 1)
                        jpy_diag = f'ok_db({sid})'
                        break
            except Exception:
                pass
        if jpy_pct is None:
            jpy_pct, jpy_diag = _query_jpy_cot_csv()
        diag['jpy_cot'] = jpy_diag

        if jpy_pct is not None:
            if jpy_pct > 90:
                score += 40
            elif jpy_pct > 80:
                score += 25
            details['JPY_COT_pct'] = jpy_pct
        else:
            details['JPY_COT_pct'] = f'N/A ({jpy_diag})'

        # 2. BTC 资金费率
        try:
            df = pd.read_sql_query(
                "SELECT value FROM observations WHERE series_id='BTC_FUNDING_RATE_1H' ORDER BY timestamp DESC LIMIT 500",
                conn
            )
            if len(df) >= 20:
                vals = df['value'].astype(float)
                pct = (vals < float(vals.iloc[0])).mean() * 100
                if pct > 95:
                    score += 30
                elif pct > 85:
                    score += 15
                details['BTC_FR_pct'] = round(pct, 1)
            else:
                details['BTC_FR_pct'] = 'N/A'
        except Exception as e:
            details['BTC_FR_pct'] = f'N/A ({str(e)[:20]})'

        # 3. PCR：SQLite 优先，CSV 兜底
        pcr_val, pcr_diag = None, None
        if _table_exists(conn, 'deribit_skew'):
            cols = _get_columns(conn, 'deribit_skew')
            for c in ['pcr', 'pcr_25d']:
                if c in cols:
                    try:
                        df = pd.read_sql_query(f"SELECT {c} AS pcr FROM deribit_skew ORDER BY rowid DESC LIMIT 1", conn)
                        if not df.empty and pd.notna(df.iloc[0]['pcr']):
                            pcr_val = float(df.iloc[0]['pcr'])
                            pcr_diag = f'ok_db({c})'
                            break
                    except Exception:
                        pass
        if pcr_val is None:
            pcr_val, pcr_diag = _query_pcr_csv()
        diag['pcr'] = pcr_diag

        if pcr_val is not None:
            if pcr_val > 1.2:
                score += 20
            elif pcr_val > 0.9:
                score += 10
            details['PCR'] = round(pcr_val, 3)
        else:
            details['PCR'] = f'N/A ({pcr_diag})'

        # 4. ETF 资金流
        try:
            tlt = _get_pct(conn, 'TLT_VOLUME')
            gld = _get_pct(conn, 'GLD_VOLUME')
            details['TLT_vol_pct'] = tlt if tlt is not None else 'N/A'
            details['GLD_vol_pct'] = gld if gld is not None else 'N/A'
            if tlt is not None and gld is not None:
                if tlt > 80 and gld > 80:
                    score += 10
                elif tlt > 80 or gld > 80:
                    score += 5
        except Exception as e:
            details['ETF_flow'] = f'ERR:{str(e)[:20]}'

        conn.close()
    except Exception as e:
        print(f"  ⚠️ Crowding 引擎异常: {e}")

    score = min(score, 100)

    if score >= 70:
        level, action = 'EXTREME', '🚨 拥挤度极端：警惕踩踏式去杠杆'
    elif score >= 50:
        level, action = 'HIGH', '⚠️ 拥挤度高：多头/空头任一方向过度拥挤'
    elif score >= 30:
        level, action = 'MEDIUM', '🟡 拥挤度中等：常规监控'
    else:
        level, action = 'LOW', '🟢 拥挤度低：筹码分布正常'

    result = {
        'asof': asof,
        'score': round(score, 1),
        'level': level,
        'action': action,
        'details': details,
        'diag': diag
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
    print(f"  诊断: {r['diag']}")
    print(f"{'='*60}\n")