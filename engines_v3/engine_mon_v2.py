"""engines_v3/engine_mon_v2.py - MON升级版（含Policy Repricing）+ 走代理层 + 严格数据校验"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.data_proxy import load as proxy_load

DB_PATH = 'data/macro.db'


def compute_mon_v2(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  MON V2 Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        def _load_proxy(sid, limit=120):
            """🆕 走数据代理层，自动享受主备源降级"""
            try:
                s = proxy_load(conn, sid, limit=limit, strict_fresh=False, verbose=False)
                if s is not None and not s.empty:
                    return s
            except Exception as e:
                print(f"  ⚠️ [MON_V2] {sid} 代理层加载失败，尝试直读: {str(e)[:80]}")

            # 回退：直读 SQLite 表
            for col in ['timestamp', 'date', 'obs_ts']:
                try:
                    df = pd.read_sql_query(
                        f"SELECT {col} AS dt, value FROM observations "
                        f"WHERE series_id=? ORDER BY {col} DESC LIMIT ?",
                        conn, params=(sid, limit)
                    )
                    if not df.empty:
                        df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                        df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                        return df.sort_values('dt').set_index('dt')['value'].astype(float).ffill()
                except Exception:
                    continue
            return pd.Series(dtype=float)

        fedfunds = _load_proxy('FEDFUNDS', 120)
        yc2y = _load_proxy('YC2Y', 60)
        yc10y = _load_proxy('YC10Y', 60)
        us10y2y = _load_proxy('US_10Y_2Y_SPREAD', 60)
    finally:
        conn.close()

    # 强制校验 FEDFUNDS 新鲜度
    if len(fedfunds) < 1:
        print("  🚨 [FAIL] FEDFUNDS 数据完全缺失，MON 引擎强制降级。")
        return {'engine_id': 'MON_V2', 'composite': 0.0, 'direction': 'UNKNOWN', 'components': {}}

    last_ff_date = pd.to_datetime(fedfunds.index[-1])
    days_lag = (datetime.now() - last_ff_date).days
    if days_lag > 45:
        print(f"  🚨 [FAIL] FEDFUNDS 数据过期 (滞后 {days_lag} 天 > 45d)，MON 引擎强制降级，拒绝输出虚假 Composite。")
        return {'engine_id': 'MON_V2', 'composite': 0.0, 'direction': 'UNKNOWN', 'components': {}}

    # ============ 1. MON_LEVEL ============
    mon_level = 0.0
    ff_used = None
    if len(fedfunds) >= 1:
        valid_ff = fedfunds[fedfunds < 20]
        if len(valid_ff) >= 1:
            ff = float(valid_ff.iloc[-1])
            ff_used = ff
            if ff > 4.5:
                mon_level = 1.5
            elif ff > 3.5:
                mon_level = 1.0
            elif ff > 2.5:
                mon_level = 0.5
            else:
                mon_level = 0.0
    print(f"  MON_LEVEL: {mon_level:.3f} (FEDFUNDS={ff_used if ff_used else 'N/A'}%)")

    # ============ 2. MON_DIRECTION ============
    mon_direction = 0.0
    if len(yc2y) >= 20:
        y2_now = float(yc2y.iloc[-1])
        y2_20d = float(yc2y.iloc[-20])
        if not pd.isna(y2_now) and not pd.isna(y2_20d):
            y2_chg = y2_now - y2_20d
            mon_direction = np.clip(y2_chg * 10, -2.0, 2.0)
    print(f"  MON_DIRECTION: {mon_direction:.3f} (2Y 20D变化)")

    # ============ 3. MON_REPRICING ============
    mon_repricing = 0.0
    if len(yc2y) >= 10:
        v5d_now = float(yc2y.iloc[-1])
        v5d_5d = float(yc2y.iloc[-5])
        v5d_prev_now = float(yc2y.iloc[-5])
        v5d_prev_10d = float(yc2y.iloc[-10])

        if not pd.isna(v5d_now) and not pd.isna(v5d_5d) and not pd.isna(v5d_prev_10d):
            v5d = v5d_now - v5d_5d
            v5d_prev = v5d_prev_now - v5d_prev_10d
            repricing_bp = v5d * 100
            if abs(repricing_bp) > 20:
                mon_repricing = np.clip(repricing_bp / 20, -3.0, 3.0)
            else:
                mon_repricing = repricing_bp / 20
    print(f"  MON_REPRICING: {mon_repricing:.3f} (5日重定价速度)")

    # ============ 4. MON_PERSISTENCE ============
    mon_persistence = 0.0
    if len(us10y2y) >= 1:
        spread = float(us10y2y.iloc[-1])
        if not pd.isna(spread):
            if spread < 0:
                mon_persistence = min(abs(spread) / 1.0, 2.0)
    print(f"  MON_PERSISTENCE: {mon_persistence:.3f} (10Y-2Y倒挂深度)")

    # ============ 5. MON_SURPRISE ============
    mon_surprise = 0.0
    if len(yc2y) >= 6:
        y2_now = float(yc2y.iloc[-1])
        y2_prev = float(yc2y.iloc[-2])
        if not pd.isna(y2_now) and not pd.isna(y2_prev):
            y2_chg_1d = (y2_now - y2_prev) * 100
            if abs(y2_chg_1d) > 10:
                mon_surprise = np.clip(y2_chg_1d / 10, -2.0, 2.0)
    print(f"  MON_SURPRISE: {mon_surprise:.3f} (1日变化)")

    # ============ 综合 MON_Composite ============
    mon_composite = (
        0.40 * mon_level +
        0.20 * mon_direction +
        0.25 * mon_repricing +
        0.10 * mon_persistence +
        0.05 * mon_surprise
    )

    if pd.isna(mon_composite):
        mon_composite = 0.0

    if mon_composite > 1.5:
        direction = 'EXTREME_TIGHT'
    elif mon_composite > 1.0:
        direction = 'TIGHT'
    elif mon_composite > 0.5:
        direction = 'TIGHTENING'
    elif mon_composite > -0.5:
        direction = 'NEUTRAL'
    elif mon_composite > -1.0:
        direction = 'EASING'
    else:
        direction = 'EXTREME_EASING'

    result = {
        'engine_id': 'MON_V2',
        'composite': round(mon_composite, 4),
        'direction': direction,
        'components': {
            'LEVEL': round(mon_level, 3),
            'DIRECTION': round(mon_direction, 3),
            'REPRICING': round(mon_repricing, 3),
            'PERSISTENCE': round(mon_persistence, 3),
            'SURPRISE': round(mon_surprise, 3),
        },
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_mon_v2 (
            asof_date TEXT PRIMARY KEY,
            composite REAL, direction TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO engine_mon_v2
        (asof_date, composite, direction, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, mon_composite, direction, json.dumps(result['components'])))
    conn.commit()
    conn.close()

    print(f"\n  MON Composite: {mon_composite:.4f} ({direction})")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    compute_mon_v2(asof)