# -*- coding: utf-8 -*-
"""tools/compute_percentile.py - 直接从 observations 计算历史分位 (v3: 彻底消除未来函数与防断更)"""
import sqlite3
import pandas as pd
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'macro.db')

SERIES_MAP = {
    'BAMLH0A0HYM2': 'HY_OAS',
    'VIX': 'VIX', 'YC10Y': 'US_10Y', 'YC2Y': 'US_2Y', 'YC30Y': 'US_30Y',
    'CPIAUCSL': 'CPI', 'FEDFUNDS': 'FEDFUNDS', 'UNRATE': 'UNRATE',
    'RRPONTSYD': 'RRP', 'RRP_BALANCE': 'RRP',
    'SOFR': 'SOFR', 'EFFR': 'EFFR', 'DTWEXBGS': 'DXY_BROAD', 'DXY_PROXY': 'DXY_PROXY',
    'CN_M1_YOY': 'CN_M1_YOY', 'CN_M2_YOY': 'CN_M2_YOY', 'CN_PMI_MFG': 'CN_PMI_MFG', 'CN_10Y_YIELD': 'CN_10Y_YIELD',
    'JP_10Y': 'JP_10Y', 'JP_CPI_YOY': 'JP_CPI_YOY', 'DE_10Y': 'DE_10Y', 'EU_HICP_YOY': 'EU_HICP_YOY',
    'USD_JPY': 'USD_JPY', 'EUR_USD': 'EUR_USD', 'USDCNY_MID': 'USDCNY_MID',
    'BTC_FUNDING_RATE_1H': 'BTC_FUNDING_RATE_1H', 'BTC_OI_VALUE_HIST': 'BTC_OI_VALUE_HIST'
}

SANITY_CHECKS = {
    'PAYEMS': (100000, 300000), 'PAYROLLS': (100000, 300000),
    'US_CPI_YOY': (-10, 50), 'CPI': (-10, 50), 'UNRATE': (0, 30),
    'YC10Y': (-5, 20), 'YC2Y': (-5, 20), 'RRP_BALANCE': (0, 5000000),
    'CN_M1_YOY': (-30, 50), 'CN_M2_YOY': (-10, 50), 'CN_PMI_MFG': (30, 70),
    'CN_10Y_YIELD': (0, 10), 'JP_10Y': (-1, 10), 'JP_CPI_YOY': (-5, 20),
    'DE_10Y': (-2, 15), 'EU_HICP_YOY': (-5, 20), 'USD_JPY': (50, 300), 'EUR_USD': (0.5, 2.0),
    'USDCNY_MID': (5.0, 10.0)
}

def calc_pct_z(series, window):
    """计算分位数与 Z-Score（严格消除未来函数）"""
    # 🆕 核心修复：如果数据量不足窗口的 70%，说明数据断档严重，不计算分位
    if len(series) < window * 0.7:
        return None, None
    
    # 强制取最近的 window 条数据（已经是在 as_of 日期之前）
    sub = series.tail(window) if len(series) >= window else series
    if len(sub) < 20: 
        return None, None
    
    latest = float(series.iloc[-1])
    
    # 计算严格小于当前值的比例
    pct = float((sub < latest).mean() * 100)
    
    # 计算 Z-Score：使用当前窗口的均值和标准差，绝不能用全样本
    mean = float(sub.mean())
    std = float(sub.std())
    z = (latest - mean) / std if std > 0 else 0.0
    
    return round(pct, 2), round(z, 4)

def main():
    # 设定计算基准日（默认今天，可以传入历史日期用于回测）
    as_of = datetime.now().strftime('%Y-%m-%d')
    print(f"🎯 分位计算基准日: {as_of}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS series_percentile (series_id TEXT NOT NULL, as_of_date TEXT NOT NULL, value REAL, z_score_1y REAL, z_score_5y REAL, pct_1y REAL, pct_5y REAL, PRIMARY KEY (series_id, as_of_date))""")

    existing = set(r[0] for r in conn.execute("SELECT DISTINCT series_id FROM observations").fetchall())
    targets = [(sid, SERIES_MAP.get(sid, sid)) for sid in existing]

    best = {}
    for sid, mapped in targets:
        # 🆕 核心修复：强制加上 timestamp <= as_of，防止未来数据被计入！
        # 强制 ASC 排序，保证最后一条就是最新数据
        query = "SELECT timestamp AS dt, value FROM observations WHERE series_id=? AND timestamp <= ? ORDER BY timestamp ASC"
        df = pd.read_sql_query(query, conn, params=(sid, as_of))
        
        if df.empty: continue
        
        # 清洗时间戳
        df['dt'] = pd.to_datetime(df['dt'], format='mixed', errors='coerce')
        df['dt'] = df['dt'].dt.strftime('%Y-%m-%d')
        df = df.dropna(subset=['dt', 'value'])
        df = df.drop_duplicates(subset=['dt'], keep='first')
        df = df.sort_values('dt').set_index('dt')['value'].astype(float)
        
        if len(df) < 20: continue
        
        # 如果同一个映射指标有多个源，取历史数据最长的那个
        if mapped not in best or len(df) > len(best[mapped][1]):
            best[mapped] = (sid, df)

    print(f"🎯 将计算 {len(best)} 个映射序列的分位\n")
    for mapped, (sid, series) in best.items():
        latest_date = series.index[-1]
        latest_value = float(series.iloc[-1])
        
        if mapped in SANITY_CHECKS or sid in SANITY_CHECKS:
            min_val, max_val = SANITY_CHECKS.get(sid, SANITY_CHECKS.get(mapped))
            if not (min_val <= latest_value <= max_val):
                print(f"  🚨 [脏数据拦截] {mapped} (源:{sid}) 值={latest_value} 超出范围，已跳过！")
                continue
                
        # 1年窗口 252 条，5年窗口 1260 条
        pct_1y, z_1y = calc_pct_z(series, 252)
        pct_5y, z_5y = calc_pct_z(series, 1260)

        conn.execute("""INSERT OR REPLACE INTO series_percentile (series_id, as_of_date, value, z_score_1y, z_score_5y, pct_1y, pct_5y) VALUES (?, ?, ?, ?, ?, ?, ?)""", (mapped, latest_date, latest_value, z_1y, z_5y, pct_1y, pct_5y))
        
        is_fallback = (sid != mapped) and (mapped == 'RRP' and sid != 'RRPONTSYD')
        tag = " (降级)" if is_fallback else ""
        
        p1_str = f"{pct_1y:>6}" if pct_1y is not None else "   N/A"
        p5_str = f"{pct_5y:>6}" if pct_5y is not None else "   N/A"
        
        flag = "🔴" if (pct_5y is not None and pct_5y > 90) else "🟡" if (pct_5y is not None and pct_5y > 70) else "🟢"
        if pct_5y is None: flag = "⚪"
        
        print(f"  {flag} {mapped:20s}{tag} (源:{sid:18s}) 值={latest_value:>12.4f}  1y_pct={p1_str}  5y_pct={p5_str}  (总历史:{len(series)}条)")

    conn.commit()
    conn.close()
    print("\n✅ 分位计算完成，已写入 series_percentile（未来函数已彻底消除）")

if __name__ == "__main__":
    main()