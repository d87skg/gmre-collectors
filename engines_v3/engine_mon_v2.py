"""engines_v3/engine_mon_v2.py - MON升级版（含Policy Repricing）"""
import requests
import sqlite3
import io
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
PROXIES = None


def compute_mon_v2(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  MON V2 Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        def _load(sid, limit=120):
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

        fedfunds = _load('FEDFUNDS', 60)
        yc2y = _load('YC2Y', 60)
        yc10y = _load('YC10Y', 60)
        us10y2y = _load('US_10Y_2Y_SPREAD', 60)
    finally:
        conn.close()

       # ============ 1. MON_LEVEL（政策利率绝对水平）============
    mon_level = 0.0
    ff_used = None
    if len(fedfunds) >= 1:
        # 关键修复：过滤掉污染数据（联邦基金利率一定 < 20%）
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
        else:
            # 全部污染，用默认值
            ff = 3.75
            ff_used = ff
            mon_level = 1.0
            print(f"  ⚠️ FEDFUNDS数据污染，使用默认值{ff}%")
    print(f"  MON_LEVEL: {mon_level:.3f} (FEDFUNDS={ff_used if ff_used else 'N/A'}%)")

    # ============ 2. MON_DIRECTION（政策方向）============
    mon_direction = 0.0
    if len(yc2y) >= 20:
        y2_chg = float(yc2y.iloc[-1] - yc2y.iloc[-20])
        # 2Y收益率上升=货币收紧
        mon_direction = np.clip(y2_chg * 10, -2.0, 2.0)
    print(f"  MON_DIRECTION: {mon_direction:.3f} (2Y 20D变化)")

    # ============ 3. MON_REPRICING（政策预期重定价速度）============
    # 代理：2Y收益率5日变化的速度
    mon_repricing = 0.0
    if len(yc2y) >= 10:
        v5d = float(yc2y.iloc[-1] - yc2y.iloc[-5])
        v5d_prev = float(yc2y.iloc[-5] - yc2y.iloc[-10])
        # 5日变化量（单位bp）
        repricing_bp = v5d * 100
        # 加速度
        accel = (v5d - v5d_prev) * 100

        if abs(repricing_bp) > 20:
            mon_repricing = np.clip(repricing_bp / 20, -3.0, 3.0)
        else:
            mon_repricing = repricing_bp / 20
    print(f"  MON_REPRICING: {mon_repricing:.3f} (5日重定价速度)")

    # ============ 4. MON_PERSISTENCE（加息持续性）============
    # 用10Y-2Y利差判断（负值=倒挂，说明紧缩过度）
    mon_persistence = 0.0
    if len(us10y2y) >= 1:
        spread = float(us10y2y.iloc[-1])
        # 倒挂越深，紧缩持续性越强
        if spread < 0:
            mon_persistence = min(abs(spread) / 1.0, 2.0)
    print(f"  MON_PERSISTENCE: {mon_persistence:.3f} (10Y-2Y倒挂深度)")

    # ============ 5. MON_SURPRISE（vs 市场预期）============
    # 暂用5日变化作为代理
    mon_surprise = 0.0
    if len(yc2y) >= 6:
        y2_chg_1d = float(yc2y.iloc[-1] - yc2y.iloc[-2]) * 100  # bp
        if abs(y2_chg_1d) > 10:
            mon_surprise = np.clip(y2_chg_1d / 10, -2.0, 2.0)
    print(f"  MON_SURPRISE: {mon_surprise:.3f} (1日变化)")

    # ============ 综合MON_Composite ============
    mon_composite = (
        0.40 * mon_level
        + 0.20 * mon_direction
        + 0.25 * mon_repricing
        + 0.10 * mon_persistence
        + 0.05 * mon_surprise
    )

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
        }
    }

    # 落盘
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