"""engines_v3/contagion_engine.py - 跨资产相关性突变监测"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=180):
    for date_col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {date_col} AS dt, value FROM observations "
                f"WHERE series_id=? ORDER BY {date_col} DESC LIMIT ?",
                conn, params=(sid, limit)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def compute_contagion(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Contagion Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        # 加载主要资产
        assets = {
            'SP500': 'S&P',
            'YC10Y': 'US10Y',
            'GOLD_PRICE': 'GOLD',
            'WTI_OIL': 'WTI',
            'USD_JPY': 'USDJPY',
            'VIX': 'VIX',
        }
        series = {}
        for sid, name in assets.items():
            s = _load(conn, sid, 180)
            if len(s) >= 60:
                series[name] = s
    finally:
        conn.close()

    if len(series) < 4:
        print("  ⚠️ 数据不足")
        return {'asof': asof, 'status': 'INSUFFICIENT_DATA'}

    # 对齐
    df = pd.DataFrame(series).dropna()
    if len(df) < 30:
        return {'asof': asof, 'status': 'INSUFFICIENT_DATA'}

    # 收益率
    returns = df.pct_change().dropna()

    # 1. 60天相关性矩阵
    corr_60 = returns.tail(60).corr()
    # 2. 20天相关性矩阵
    corr_20 = returns.tail(20).corr()
    # 3. 5天相关性矩阵
    corr_5 = returns.tail(5).corr() if len(returns) >= 5 else None

    # 4. 相关性突变检测
    avg_corr_60 = (corr_60.values.sum() - np.trace(corr_60.values)) / (corr_60.shape[0] * (corr_60.shape[0] - 1))
    avg_corr_20 = (corr_20.values.sum() - np.trace(corr_20.values)) / (corr_20.shape[0] * (corr_20.shape[0] - 1))
    avg_corr_5 = (corr_5.values.sum() - np.trace(corr_5.values)) / (corr_5.shape[0] * (corr_5.shape[0] - 1)) if corr_5 is not None else 0

    correlation_break = avg_corr_20 - avg_corr_60
    extreme_break = avg_corr_5 - avg_corr_60

    # 5. 危机相关性特征：所有资产同时下跌
    recent_5d_returns = returns.tail(5)
    all_negative = (recent_5d_returns < 0).all().all()
    all_negative_count = (recent_5d_returns < 0).sum().sum()

    # 6. 状态判定
    if avg_corr_20 > 0.5 and avg_corr_5 > 0.6:
        status = 'CONTAGION'
    elif correlation_break > 0.3:
        status = 'CORRELATION_BREAK'
    elif avg_corr_20 > 0.35:
        status = 'CO-MOVEMENT'
    else:
        status = 'NORMAL'

    print(f"  [1/2] 相关性分析：")
    print(f"    60D平均相关性: {avg_corr_60:.3f}")
    print(f"    20D平均相关性: {avg_corr_20:.3f}")
    print(f"    5D平均相关性:  {avg_corr_5:.3f}")
    print(f"    相关性突变:   {correlation_break:+.3f}")
    print(f"    极端突变:     {extreme_break:+.3f}")

    print(f"\n  [2/2] 危机特征：")
    print(f"    5日内负收益数: {all_negative_count}/{recent_5d_returns.size}")
    print(f"    全线下跌: {'是' if all_negative else '否'}")

    print(f"\n  状态: {status}")

    result = {
        'asof': asof,
        'status': status,
        'avg_corr_60d': round(float(avg_corr_60), 4),
        'avg_corr_20d': round(float(avg_corr_20), 4),
        'avg_corr_5d': round(float(avg_corr_5), 4),
        'correlation_break': round(float(correlation_break), 4),
        'extreme_break': round(float(extreme_break), 4),
        'all_negative_5d': bool(all_negative),
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS contagion_engine (
            asof_date TEXT PRIMARY KEY,
            status TEXT, avg_corr_60d REAL, avg_corr_20d REAL, corr_break REAL,
            detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO contagion_engine
        (asof_date, status, avg_corr_60d, avg_corr_20d, corr_break, detail)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asof, status, result['avg_corr_60d'], result['avg_corr_20d'],
          result['correlation_break'], json.dumps(result)))
    conn.commit()
    conn.close()

    print(f"{'='*60}\n")
    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    compute_contagion(asof)