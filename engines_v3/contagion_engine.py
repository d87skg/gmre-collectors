"""engines_v3/contagion_engine.py - 跨资产相关性突变监测 [修复版 + 资产加载诊断]"""
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
        # 注意：去掉了 VIX 和 10Y，因为它们不是资产价格，不能算 pct_change
        assets = {
            'SP500': 'S&P',
            'GOLD_PRICE': 'GOLD',
            'WTI_OIL': 'WTI',
            'USD_JPY': 'USDJPY'
        }
        series = {}
        for sid, name in assets.items():
            s = _load(conn, sid, 180)
            if len(s) >= 60:
                series[name] = s
                print(f"  [加载] {name:8s} ({sid:12s}) {len(s):4d} 条  最新 {s.index[-1].strftime('%Y-%m-%d')}")
            else:
                print(f"  [跳过] {name:8s} ({sid:12s}) 只有 {len(s):3d} 条 (<60)")
    finally:
        conn.close()

    if len(series) < 3:
        print("  ⚠️ 数据不足 (有效资产少于 3 个)")
        return {'asof': asof, 'status': 'INSUFFICIENT_DATA'}

    # 用 inner join 对齐，但允许每个资产自身长度不一
    df = pd.DataFrame(series)
    # 向前填充缺失值 (解决周末/节假日错位问题)
    df = df.ffill().dropna()

    if len(df) < 30:
        print(f"  ⚠️ 对齐后的数据长度不足: {len(df)} 条")
        return {'asof': asof, 'status': 'INSUFFICIENT_DATA'}

    # 收益率
    returns = df.pct_change().dropna()

    # 计算相关性矩阵 (加入 fillna(0) 防止因某资产长期停牌导致方差为0产生 NaN)
    corr_60 = returns.tail(60).corr().fillna(0)
    corr_20 = returns.tail(20).corr().fillna(0)
    corr_5 = returns.tail(5).corr().fillna(0) if len(returns) >= 5 else corr_20

    def get_avg_corr(corr_matrix):
        vals = corr_matrix.values
        # 剔除对角线
        return (vals.sum() - np.trace(vals)) / (vals.shape[0] * (vals.shape[0] - 1))

    avg_corr_60 = get_avg_corr(corr_60)
    avg_corr_20 = get_avg_corr(corr_20)
    avg_corr_5 = get_avg_corr(corr_5)

    correlation_break = avg_corr_20 - avg_corr_60
    extreme_break = avg_corr_5 - avg_corr_60

    recent_5d_returns = returns.tail(5)
    all_negative = (recent_5d_returns < 0).all().all()
    all_negative_count = (recent_5d_returns < 0).sum().sum()

    if avg_corr_20 > 0.4 and avg_corr_5 > 0.5:
        status = 'CONTAGION'
    elif correlation_break > 0.3:
        status = 'CORRELATION_BREAK'
    elif avg_corr_20 > 0.3:
        status = 'CO-MOVEMENT'
    else:
        status = 'NORMAL'

    print(f"  [1/2] 相关性分析（参与资产: {list(df.columns)}）：")
    print(f"    60D平均相关性: {avg_corr_60:.3f}")
    print(f"    20D平均相关性: {avg_corr_20:.3f}")
    print(f"    5D平均相关性:  {avg_corr_5:.3f}")
    print(f"    相关性突变:   {correlation_break:+.3f}")

    print(f"\n  [2/2] 危机特征：")
    print(f"    5日内负收益数: {all_negative_count}/{recent_5d_returns.size}")

    print(f"\n  状态: {status}")

    result = {
        'asof': asof, 'status': status, 'avg_corr_60d': round(float(avg_corr_60), 4),
        'avg_corr_20d': round(float(avg_corr_20), 4), 'avg_corr_5d': round(float(avg_corr_5), 4),
        'correlation_break': round(float(correlation_break), 4), 'extreme_break': round(float(extreme_break), 4),
        'all_negative_5d': bool(all_negative),
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS contagion_engine (asof_date TEXT PRIMARY KEY, status TEXT, avg_corr_60d REAL, avg_corr_20d REAL, corr_break REAL, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO contagion_engine (asof_date, status, avg_corr_60d, avg_corr_20d, corr_break, detail) VALUES (?, ?, ?, ?, ?, ?)""",
                 (asof, status, result['avg_corr_60d'], result['avg_corr_20d'], result['correlation_break'], json.dumps(result)))
    conn.commit()
    conn.close()
    print(f"{'='*60}\n")
    return result


if __name__ == "__main__":
    compute_contagion(datetime.now().strftime('%Y-%m-%d'))