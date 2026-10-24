"""engines_v3/velocity_engine.py - Velocity/Acceleration/Breadth/Correlation"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=120):
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


def compute_velocity(series):
    """计算 Level/Velocity/Acceleration"""
    if len(series) < 21:
        return None
    s = series.dropna()
    level = float(s.iloc[-1])
    v1d = float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else 0
    v5d = float(s.iloc[-1] - s.iloc[-min(5, len(s))])
    v20d = float(s.iloc[-1] - s.iloc[-min(20, len(s))])
    # 加速度：5日变化率的变化
    if len(s) >= 10:
        v5d_prev = float(s.iloc[-min(5, len(s))] - s.iloc[-min(10, len(s))])
        accel = v5d - v5d_prev
    else:
        accel = 0
    return {
        'level': round(level, 4),
        'v1d': round(v1d, 4),
        'v5d': round(v5d, 4),
        'v20d': round(v20d, 4),
        'accel_5d': round(accel, 4)
    }


def compute_breadth(conn):
    """计算 breadth：多少资产同时恶化"""
    watchlist = {
        'SP500': 'up_is_good',
        'WTI_OIL': 'up_is_bad',
        'YC10Y': 'up_is_bad',
        'USD_JPY': 'up_is_good',
        'VIX': 'up_is_bad',
        'HY_SPREAD': 'up_is_bad',
    }
    worsening_count = 0
    total_count = 0
    details = []

    for sid, direction in watchlist.items():
        s = _load(conn, sid, 20)
        if len(s) < 6:
            continue
        # 5日变化
        chg = float(s.iloc[-1] - s.iloc[-min(5, len(s))])

        if direction == 'up_is_bad':
            is_worsening = chg > 0
        else:
            is_worsening = chg < 0

        if is_worsening:
            worsening_count += 1
        total_count += 1
        details.append(f"{sid}: {'恶化' if is_worsening else '改善'}")

    breadth = (worsening_count / total_count * 100) if total_count > 0 else 0
    return {
        'breadth_pct': round(breadth, 1),
        'worsening': worsening_count,
        'total': total_count,
        'details': details
    }


def compute_correlation(conn):
    """计算股债相关性（60天滚动）"""
    try:
        spx = _load(conn, 'SP500', 90)
        y10 = _load(conn, 'YC10Y', 90)
        if len(spx) < 30 or len(y10) < 30:
            return None

        # 收益率
        spx_ret = spx.pct_change().dropna()
        y10_chg = y10.diff().dropna()

        # 对齐日期
        df = pd.concat([spx_ret.rename('spx'), y10_chg.rename('y10')], axis=1).dropna()
        if len(df) < 30:
            return None

        # 60天滚动相关性
        corr_60 = df.tail(60).corr().iloc[0, 1]
        corr_20 = df.tail(20).corr().iloc[0, 1]
        corr_5 = df.tail(5).corr().iloc[0, 1] if len(df) >= 5 else None

        # 相关性突变检测：20天vs60天差异
        corr_break = abs(corr_20 - corr_60) if corr_60 and corr_20 else 0

        return {
            'corr_60d': round(float(corr_60), 3),
            'corr_20d': round(float(corr_20), 3),
            'corr_5d': round(float(corr_5), 3) if corr_5 is not None else None,
            'corr_break': round(float(corr_break), 3)
        }
    except Exception as e:
        return None


def evaluate_velocity(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Velocity Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        # 关键序列的 velocity
        print("[1/3] 计算关键序列速度...")
        key_series = {
            'YC10Y':   'US 10Y',
            'USD_JPY': 'USDJPY',
            'WTI_OIL': 'WTI原油',
            'SP500':   'S&P500',
            'VIX':     'VIX',
            'HY_SPREAD': 'HY利差'
        }
        velocity_data = {}
        for sid, name in key_series.items():
            s = _load(conn, sid, 120)
            if len(s) >= 21:
                v = compute_velocity(s)
                velocity_data[sid] = v
                print(f"  [{name}] L={v['level']:.3f} V1D={v['v1d']:+.3f} V5D={v['v5d']:+.3f} V20D={v['v20d']:+.3f} A={v['accel_5d']:+.3f}")

        # Breadth
        print("\n[2/3] 计算 Breadth...")
        breadth = compute_breadth(conn)
        print(f"  恶化比例: {breadth['breadth_pct']}% ({breadth['worsening']}/{breadth['total']})")
        for d in breadth['details']:
            print(f"    {d}")

        # Correlation
        print("\n[3/3] 计算股债相关性...")
        corr = compute_correlation(conn)
        if corr:
            print(f"  60D相关性: {corr['corr_60d']}")
            print(f"  20D相关性: {corr['corr_20d']}")
            print(f"  5D相关性:  {corr['corr_5d']}")
            print(f"  相关性突变: {corr['corr_break']}")

        result = {
            'asof': asof,
            'velocity': velocity_data,
            'breadth': breadth,
            'correlation': corr
        }
    finally:
        conn.close()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS velocity_engine (
            asof_date TEXT PRIMARY KEY,
            breadth_pct REAL, corr_60d REAL, corr_break REAL, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO velocity_engine
        (asof_date, breadth_pct, corr_60d, corr_break, detail)
        VALUES (?, ?, ?, ?, ?)
    """, (asof, breadth['breadth_pct'],
          corr['corr_60d'] if corr else None,
          corr['corr_break'] if corr else None,
          json.dumps(result)))
    conn.commit()
    conn.close()

    print(f"\n{'='*60}\n")
    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    evaluate_velocity(asof)