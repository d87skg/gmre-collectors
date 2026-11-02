"""engines_v3/positioning_engine.py - Positioning Engine（纯本地数据版）"""
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


def evaluate_positioning(asof: str) -> dict:
    """用数据库已有数据评估 Positioning Stress"""
    print(f"\n{'='*60}")
    print(f"  Positioning Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        stress_score = 0.0
        details = []

        # ============ 1. VIX水平 + VIX变化（恐慌指数）============
        vix = _load(conn, 'VIX', 120)
        if len(vix) >= 20:
            vix_now = float(vix.iloc[-1])
            vix_mean_60 = float(vix.tail(60).mean())
            vix_20d_chg = float(vix.iloc[-1] - vix.iloc[-min(20, len(vix))])

            # VIX绝对水平
            if vix_now > 25:
                score = 30
                stress_score += score
                details.append(f"VIX={vix_now:.1f} >25（恐慌）, +{score}")
            elif vix_now > 20:
                score = 15
                stress_score += score
                details.append(f"VIX={vix_now:.1f} >20（警戒）, +{score}")

            # VIX快速抬升
            if vix_20d_chg > 5:
                score = 20
                stress_score += score
                details.append(f"VIX 20日+{vix_20d_chg:.1f}（快速抬升）, +{score}")

        # ============ 2. HY利差（信用恐慌）============
        hyg = _load(conn, 'HY_SPREAD', 120)
        if len(hyg) >= 20:
            hy_now = float(hyg.iloc[-1])
            hy_mean_60 = float(hyg.tail(60).mean())
            hy_20d_chg = float(hyg.iloc[-1] - hyg.iloc[-min(20, len(hyg))])

            if hy_now > 4.0:
                score = 25
                stress_score += score
                details.append(f"HY利差={hy_now:.2f} >4.0（信用恐慌）, +{score}")
            elif hy_now > 3.5:
                score = 15
                stress_score += score
                details.append(f"HY利差={hy_now:.2f} >3.5（信用警戒）, +{score}")

            if hy_20d_chg > 0.5:
                score = 15
                stress_score += score
                details.append(f"HY利差 20日+{hy_20d_chg:.2f}（快速走阔）, +{score}")

        # ============ 3. USDJPY加速度（日元套利压力）============
        usdjpy = _load(conn, 'USD_JPY', 120)
        if len(usdjpy) >= 20:
            usdjpy_now = float(usdjpy.iloc[-1])
            usdjpy_5d = float(usdjpy.iloc[-1] - usdjpy.iloc[-min(5, len(usdjpy))])
            usdjpy_20d = float(usdjpy.iloc[-1] - usdjpy.iloc[-min(20, len(usdjpy))])

            # 日元加速升值 = 套利平仓风险
            if usdjpy_5d < -3.0:
                score = 25
                stress_score += score
                details.append(f"USDJPY 5日-{abs(usdjpy_5d):.2f}（加速升值）, +{score}")
            elif usdjpy_5d < -1.5:
                score = 15
                stress_score += score
                details.append(f"USDJPY 5日-{abs(usdjpy_5d):.2f}（升值）, +{score}")

        # ============ 4. 股债相关性（对冲失效）============
        spx = _load(conn, 'SP500', 90)
        y10 = _load(conn, 'YC10Y', 90)
        if len(spx) >= 30 and len(y10) >= 30:
            spx_ret = spx.pct_change().dropna()
            y10_chg = y10.diff().dropna()
            df = pd.concat([spx_ret.rename('spx'), y10_chg.rename('y10')], axis=1).dropna()
            if len(df) >= 20:
                corr_5 = float(df.tail(5).corr().iloc[0, 1])
                corr_20 = float(df.tail(20).corr().iloc[0, 1])
                # 5日相关性突然转正 = 对冲失效 = 系统性抛售
                if corr_5 > 0.5:
                    score = 20
                    stress_score += score
                    details.append(f"股债5日相关性={corr_5:.2f}（对冲失效）, +{score}")
                elif corr_5 > 0.2:
                    score = 10
                    stress_score += score
                    details.append(f"股债5日相关性={corr_5:.2f}（相关性上升）, +{score}")

        # 限制在 0-100
        stress_score = min(stress_score, 100)

        if stress_score >= 70:
            level = 'EXTREME'
        elif stress_score >= 50:
            level = 'HIGH'
        elif stress_score >= 30:
            level = 'MEDIUM'
        else:
            level = 'LOW'

        result = {
            'asof': asof,
            'positioning_stress': round(stress_score, 1),
            'level': level,
            'details': details
        }
    finally:
        conn.close()

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS positioning_engine (
            asof_date TEXT PRIMARY KEY,
            stress_score REAL, level TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO positioning_engine
        (asof_date, stress_score, level, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, result['positioning_stress'], result['level'], json.dumps(details)))
    conn.commit()
    conn.close()

    print(f"  Positioning Stress: {result['positioning_stress']}/100 ({result['level']})")
    if details:
        for d in details:
            print(f"    → {d}")
    else:
        print(f"    → 所有指标正常，无异常触发")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    evaluate_positioning(asof)