# -*- coding: utf-8 -*-
"""engines_v3/china_us_linkage_engine.py - 中美联动危机判定"""
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


def compute_linkage(asof: str) -> dict:
    result = {
        'asof': asof,
        'hy_oas_bp': None,
        'corr_5d': None,
        'cnh_5d_chg': None,
        'status': 'UNKNOWN',
        'action': '⚪ 数据不足，无法判定'
    }

    try:
        conn = sqlite3.connect(DB_PATH)

        # 1. HY OAS
        hy = _load(conn, 'HY_SPREAD', 30)
        if len(hy) >= 1:
            result['hy_oas_bp'] = round(float(hy.iloc[-1]) * 100, 1)

        # 2. 中美股市 5D 相关性
        spx = _load(conn, 'SP500', 60)
        csi300 = _load(conn, 'CN_CSI300', 60)
        if len(spx) >= 30 and len(csi300) >= 30:
            spx_ret = spx.pct_change().dropna()
            csi_ret = csi300.pct_change().dropna()
            merged = pd.concat([spx_ret.rename('s'), csi_ret.rename('c')],
                                axis=1, sort=True).dropna()
            if len(merged) >= 5:
                result['corr_5d'] = round(float(merged.tail(5).corr().iloc[0, 1]), 3)

        # 3. 人民币汇率 5D 变化
        cnh = _load(conn, 'USD_CNH', 30)
        if len(cnh) < 5:
            cnh = _load(conn, 'USDCNY_MID', 30)
        if len(cnh) >= 5:
            cnh_chg = (float(cnh.iloc[-1]) - float(cnh.iloc[-5])) / float(cnh.iloc[-5]) * 100
            result['cnh_5d_chg'] = round(cnh_chg, 2)

        conn.close()

        # 判定
        hy_val = result['hy_oas_bp']
        corr = result['corr_5d']

        if hy_val is not None and hy_val > 500 and corr is not None and corr > 0.5:
            result['status'] = 'GLOBAL_RESONANCE'
            result['action'] = '🚨 全球共振危机，中美同步宽松概率极高'
        elif corr is not None and corr < 0.2:
            result['status'] = 'DECOUPLING'
            result['action'] = '⚪ 中美脱钩，各看各的锚'
        else:
            result['status'] = 'MIXED'
            result['action'] = '🟡 弱联动，需关注汇率'

    except Exception as e:
        print(f"  ⚠️ 中美联动引擎异常: {e}")

    try:
        conn2 = sqlite3.connect(DB_PATH)
        conn2.execute("""CREATE TABLE IF NOT EXISTS china_us_linkage (
            asof_date TEXT PRIMARY KEY, status TEXT, detail TEXT)""")
        conn2.execute("""INSERT OR REPLACE INTO china_us_linkage
            (asof_date, status, detail) VALUES (?, ?, ?)""",
            (asof, result['status'], json.dumps(result)))
        conn2.commit()
        conn2.close()
    except Exception:
        pass

    return result


if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_linkage(asof)
    print(f"\n{'='*60}")
    print(f"  中美联动引擎 - {asof}")
    print(f"{'='*60}")
    print(f"  HY OAS: {r['hy_oas_bp']} bp")
    print(f"  5D 相关性: {r['corr_5d']}")
    print(f"  CNH 5D: {r['cnh_5d_chg']}%")
    print(f"  状态: {r['status']}")
    print(f"  {r['action']}")
    print(f"{'='*60}\n")