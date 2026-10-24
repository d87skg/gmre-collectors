# -*- coding: utf-8 -*-
"""tools/compute_percentile.py - 直接从 observations 计算历史分位（不依赖 series_history）"""
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/macro.db'

# observations 里的原始 series_id -> series_percentile 里引擎期望的名字
SERIES_MAP = {
    'BAMLH0A0HYM2': 'HY_OAS',
    'BAMLH0A1HYBB': 'HY_BB',
    'BAMLH0A3HYC':  'HY_CCC',
    'BAMLC0A4CBBB': 'IG_BBB',
    'BAMLC0A0CM':   'IG_OAS',
    'VIX':          'VIX',
    'YC10Y':        'US_10Y',
    'YC2Y':         'US_2Y',
    'YC30Y':        'US_30Y',
    'CPIAUCSL':     'CPI',
    'FEDFUNDS':     'FEDFUNDS',
    'UNRATE':       'UNRATE',
    'RRP_BALANCE':  'RRP',
    'RRPONTSYD':    'RRP',
    'SOFR':         'SOFR',
    'EFFR':         'EFFR',
    'DTWEXBGS':     'DXY_BROAD',
    'DXY_PROXY':    'DXY_PROXY',
}

def calc_pct_z(series, window):
    """计算给定窗口内的分位和 z-score"""
    sub = series.tail(window) if len(series) >= window else series
    if len(sub) < 5:
        return None, None
    latest = float(series.iloc[-1])
    pct = float((sub < latest).mean() * 100)
    mean = float(sub.mean())
    std = float(sub.std())
    z = (latest - mean) / std if std > 0 else 0.0
    return round(pct, 2), round(z, 4)

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS series_percentile (
            series_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            value REAL,
            z_score_1y REAL,
            z_score_5y REAL,
            pct_1y REAL,
            pct_5y REAL,
            PRIMARY KEY (series_id, as_of_date)
        )
    """)

    # 实际存在的 series_id
    existing = set(r[0] for r in conn.execute("SELECT DISTINCT series_id FROM observations").fetchall())
    print(f"📊 observations 中共有 {len(existing)} 个序列")

    # 构建实际要计算的列表：原始名 -> 映射名（如果映射不到就用原名）
    targets = []
    for sid in existing:
        mapped = SERIES_MAP.get(sid, sid)
        targets.append((sid, mapped))

    # 去重（比如 RRP_BALANCE 和 RRPONTSYD 都映射到 RRP，优先取数据更长的）
    best = {}
    for sid, mapped in targets:
        df = pd.read_sql_query(
            "SELECT timestamp AS dt, value FROM observations WHERE series_id=? ORDER BY timestamp",
            conn, params=(sid,)
        )
        if df.empty:
            continue
        df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
        df = df.dropna(subset=['dt', 'value']).drop_duplicates(subset=['dt'], keep='first')
        df = df.sort_values('dt').set_index('dt')['value'].astype(float)
        if len(df) < 20:
            continue
        if mapped not in best or len(df) > len(best[mapped][1]):
            best[mapped] = (sid, df)

    print(f"🎯 将计算 {len(best)} 个映射序列的分位\n")

    for mapped, (sid, series) in best.items():
        latest_date = series.index[-1].strftime('%Y-%m-%d')
        latest_value = float(series.iloc[-1])
        pct_1y, z_1y = calc_pct_z(series, 252)
        pct_5y, z_5y = calc_pct_z(series, 1260)

        conn.execute("""
            INSERT OR REPLACE INTO series_percentile
            (series_id, as_of_date, value, z_score_1y, z_score_5y, pct_1y, pct_5y)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mapped, latest_date, latest_value, z_1y, z_5y, pct_1y, pct_5y))

        flag = "🔴" if (pct_5y is not None and pct_5y > 90) else "🟡" if (pct_5y is not None and pct_5y > 70) else "🟢"
        print(f"  {flag} {mapped:12s} (源:{sid:14s}) 值={latest_value:>12.4f}  "
              f"1y_pct={pct_1y if pct_1y is not None else 'N/A':>6}  "
              f"5y_pct={pct_5y if pct_5y is not None else 'N/A':>6}")

    conn.commit()
    conn.close()
    print("\n✅ 分位计算完成，已写入 series_percentile")

if __name__ == "__main__":
    main()