# -*- coding: utf-8 -*-
"""tools/compute_percentile.py - 直接从 observations 计算历史分位"""
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/macro.db'

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
    'CN_M1_YOY':    'CN_M1_YOY',
    'CN_M2_YOY':    'CN_M2_YOY',
    'CN_PMI_MFG':   'CN_PMI_MFG',
    'CN_10Y_YIELD': 'CN_10Y_YIELD',
    # 新增日欧指标
    'JP_10Y':       'JP_10Y',
    'JP_CPI_YOY':   'JP_CPI_YOY',
    'DE_10Y':       'DE_10Y',
    'EU_HICP_YOY':  'EU_HICP_YOY',
    'USD_JPY':      'USD_JPY',
    'EUR_USD':      'EUR_USD',
    # 加密微观
    'BTC_FUNDING_RATE_1H': 'BTC_FUNDING_RATE_1H',
    'BTC_OI_VALUE_HIST':   'BTC_OI_VALUE_HIST',
    'BTC_SPOT_PRICE_1H':   'BTC_SPOT_PRICE_1H',
    'BTC_BASIS_1H':        'BTC_BASIS_1H'
}

SANITY_CHECKS = {
    'PAYEMS': (100000, 300000),
    'PAYROLLS': (100000, 300000),
    'US_CPI_YOY': (-10, 50),
    'CPI': (-10, 50),
    'UNRATE': (0, 30),
    'YC10Y': (-5, 20),
    'YC2Y': (-5, 20),
    'RRP_BALANCE': (0, 5000000),
    'CN_M1_YOY': (-30, 50),
    'CN_M2_YOY': (-10, 50),
    'CN_PMI_MFG': (30, 70),
    'CN_10Y_YIELD': (0, 10),
    'JP_10Y': (-1, 10),
    'JP_CPI_YOY': (-5, 20),
    'DE_10Y': (-2, 15),
    'EU_HICP_YOY': (-5, 20),
    'USD_JPY': (50, 300),
    'EUR_USD': (0.5, 2.0)
}

def calc_pct_z(series, window):
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
            series_id TEXT NOT NULL, as_of_date TEXT NOT NULL, value REAL,
            z_score_1y REAL, z_score_5y REAL, pct_1y REAL, pct_5y REAL,
            PRIMARY KEY (series_id, as_of_date)
        )
    """)

    existing = set(r[0] for r in conn.execute("SELECT DISTINCT series_id FROM observations").fetchall())
    print(f"📊 observations 中共有 {len(existing)} 个序列")

    targets = [(sid, SERIES_MAP.get(sid, sid)) for sid in existing]
    best = {}
    
    for sid, mapped in targets:
        df = pd.read_sql_query(
            "SELECT timestamp AS dt, value FROM observations WHERE series_id=? ORDER BY timestamp",
            conn, params=(sid,)
        )
        if df.empty: continue
        df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
        df = df.dropna(subset=['dt', 'value']).drop_duplicates(subset=['dt'], keep='first')
        df = df.sort_values('dt').set_index('dt')['value'].astype(float)
        if len(df) < 20: continue
        if mapped not in best or len(df) > len(best[mapped][1]):
            best[mapped] = (sid, df)

    print(f"🎯 将计算 {len(best)} 个映射序列的分位\n")

    for mapped, (sid, series) in best.items():
        latest_date = series.index[-1].strftime('%Y-%m-%d')
        latest_value = float(series.iloc[-1])
        
        if mapped in SANITY_CHECKS or sid in SANITY_CHECKS:
            min_val, max_val = SANITY_CHECKS.get(sid, SANITY_CHECKS.get(mapped))
            if not (min_val <= latest_value <= max_val):
                print(f"  🚨 [脏数据拦截] {mapped} (源:{sid}) 最新值={latest_value} 超出合理范围 [{min_val}, {max_val}]，已跳过！")
                continue
                
        pct_1y, z_1y = calc_pct_z(series, 252)
        pct_5y, z_5y = calc_pct_z(series, 1260)

        conn.execute("""
            INSERT OR REPLACE INTO series_percentile
            (series_id, as_of_date, value, z_score_1y, z_score_5y, pct_1y, pct_5y)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (mapped, latest_date, latest_value, z_1y, z_5y, pct_1y, pct_5y))

        flag = "🔴" if (pct_5y is not None and pct_5y > 90) else "🟡" if (pct_5y is not None and pct_5y > 70) else "🟢"
        print(f"  {flag} {mapped:<20s} (源:{sid:<18s}) 值={latest_value:>10.4f}  1y_pct={pct_1y if pct_1y else 'N/A':>6}  5y_pct={pct_5y if pct_5y else 'N/A':>6}")

    conn.commit()
    conn.close()
    print("\n✅ 分位计算完成，已写入 series_percentile")

if __name__ == "__main__":
    main()