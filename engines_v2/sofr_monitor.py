"""engines_v2/sofr_monitor.py - SOFR vs EFFR 利差监控（准备金压力预警）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'
SOFR_EFFR_SPREAD_WARNING = 3.0   # bp
SOFR_EFFR_SPREAD_CRITICAL = 10.0  # bp


def _load(conn, sid, limit=30):
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
                return df.sort_values('dt').set_index('dt')['value']
        except Exception:
            continue
    return pd.Series(dtype=float)


def check_spread(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        sofr = _load(conn, 'SOFR', 30)
        effr = _load(conn, 'EFFR', 30)
    finally:
        conn.close()

    if len(sofr) == 0 or len(effr) == 0:
        return {'asof': asof, 'status': 'NO_DATA',
                'msg': 'SOFR或EFFR数据缺失'}

    # 对齐日期后计算利差
    df = pd.concat([sofr.rename('SOFR'), effr.rename('EFFR')], axis=1).dropna()
    if df.empty:
        return {'asof': asof, 'status': 'NO_DATA', 'msg': '两序列无交集'}

    df['spread_bp'] = (df['SOFR'] - df['EFFR']) * 100

    latest = df.iloc[-1]
    spread_now = float(latest['spread_bp'])
    spread_5d = df['spread_bp'].tail(5).mean()
    spread_20d = df['spread_bp'].tail(20).mean()

    # 状态判定
    if spread_now > SOFR_EFFR_SPREAD_CRITICAL:
        status = 'CRITICAL'
        msg = f'🚨 SOFR-EFFR利差 {spread_now:.2f}bp 突破{SOFR_EFFR_SPREAD_CRITICAL}bp，准备金压力已向融通市场传导'
    elif spread_now > SOFR_EFFR_SPREAD_WARNING:
        status = 'WARNING'
        msg = f'⚠️ SOFR-EFFR利差 {spread_now:.2f}bp 超过{SOFR_EFFR_SPREAD_WARNING}bp，准备金开始趋紧'
    else:
        status = 'NORMAL'
        msg = f'✅ SOFR-EFFR利差 {spread_now:.2f}bp，准备金压力可控'

    result = {
        'asof': asof,
        'status': status,
        'msg': msg,
        'spread_now_bp': round(spread_now, 3),
        'spread_5d_avg_bp': round(float(spread_5d), 3),
        'spread_20d_avg_bp': round(float(spread_20d), 3),
        'sofr_latest': round(float(latest['SOFR']), 3),
        'effr_latest': round(float(latest['EFFR']), 3),
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sofr_monitor (
            asof_date TEXT PRIMARY KEY,
            status TEXT, spread_bp REAL, sofr REAL, effr REAL, msg TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO sofr_monitor
        (asof_date, status, spread_bp, sofr, effr, msg)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (asof, status, spread_now, float(latest['SOFR']),
          float(latest['EFFR']), msg))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = check_spread(asof)
    print(f"\n{'='*60}")
    print(f"  SOFR vs EFFR 监控 - {asof}")
    print(f"{'='*60}")
    print(f"  {result['msg']}")
    if 'spread_now_bp' in result:
        print(f"\n  SOFR={result['sofr_latest']}%  EFFR={result['effr_latest']}%")
        print(f"  利差: 当前={result['spread_now_bp']}bp  "
              f"5日均={result['spread_5d_avg_bp']}bp  "
              f"20日均={result['spread_20d_avg_bp']}bp")
    print(f"{'='*60}\n")