"""engines_v3/engine_fis_v2.py - FIS拆分版（Flow/Structural/Supply/TermPremium）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def compute_fis_v2(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  FIS V2 Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        def _load(sid, limit=60):
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

        y10 = _load('YC10Y', 60)
        y30 = _load('YC30Y', 60)
        tga = _load('TGA_BALANCE', 60)
        tga_daily = _load('TGA_DAILY', 60)
    finally:
        conn.close()

    # ============ 1. FIS_FLOW（短期财政流量）============
    # TGA释放资金（TGA下降）= 短期财政流量宽松 = FIS_FLOW负
    fis_flow = 0.0
    if len(tga) >= 5:
        tga_now = float(tga.iloc[-1])
        tga_4w = float(tga.iloc[-min(4, len(tga))])
        tga_chg = (tga_now - tga_4w) / tga_4w if tga_4w else 0
        # TGA下降 = 释放 = FIS_FLOW负值
        fis_flow = tga_chg * 10
    print(f"  FIS_FLOW: {fis_flow:+.3f} (TGA流量)")

    # ============ 2. FIS_STRUCTURAL（结构性赤字）============
    # 用10Y绝对值作为结构性财政压力的代理
    fis_structural = 0.0
    if len(y10) >= 1:
        y10_now = float(y10.iloc[-1])
        # 10Y>4%=财政压力大
        fis_structural = np.clip((y10_now - 3.0) * 2, -2.0, 3.0)
    print(f"  FIS_STRUCTURAL: {fis_structural:+.3f} (10Y水平)")

    # ============ 3. FIS_SUPPLY（国债净发行）============
    # 用30Y-10Y曲线斜率作为长端供给压力代理
    fis_supply = 0.0
    if len(y30) >= 1 and len(y10) >= 1:
        spread = float(y30.iloc[-1]) - float(y10.iloc[-1])
        # 30Y-10Y扩大 = 长端供给压力大
        if spread > 0.5:
            fis_supply = 1.0 + (spread - 0.5) * 2
        elif spread > 0:
            fis_supply = spread
        else:
            fis_supply = spread * 2
    print(f"  FIS_SUPPLY: {fis_supply:+.3f} (30Y-10Y曲线)")

    # ============ 4. FIS_TERM_PREMIUM（期限溢价）============
    # 用30Y变化率
    fis_term = 0.0
    if len(y30) >= 20:
        y30_now = float(y30.iloc[-1])
        y30_20d = float(y30.iloc[-min(20, len(y30))])
        y30_chg = (y30_now - y30_20d) * 100  # bp
        fis_term = np.clip(y30_chg / 20, -2.0, 3.0)
    print(f"  FIS_TERM_PREMIUM: {fis_term:+.3f} (30Y变化)")

    # ============ 综合FIS_Composite ============
    fis_composite = (
        0.25 * fis_flow
        + 0.30 * fis_structural
        + 0.25 * fis_supply
        + 0.20 * fis_term
    )

    if fis_composite > 1.5:
        direction = 'SEVERE_STRESS'
    elif fis_composite > 0.8:
        direction = 'STRESS'
    elif fis_composite > 0.3:
        direction = 'TIGHTENING'
    elif fis_composite > -0.3:
        direction = 'NEUTRAL'
    elif fis_composite > -0.8:
        direction = 'RELIEF'
    else:
        direction = 'STRONG_RELIEF'

    result = {
        'engine_id': 'FIS_V2',
        'composite': round(fis_composite, 4),
        'direction': direction,
        'components': {
            'FLOW': round(fis_flow, 3),
            'STRUCTURAL': round(fis_structural, 3),
            'SUPPLY': round(fis_supply, 3),
            'TERM_PREMIUM': round(fis_term, 3),
        }
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_fis_v2 (
            asof_date TEXT PRIMARY KEY,
            composite REAL, direction TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO engine_fis_v2
        (asof_date, composite, direction, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, fis_composite, direction, json.dumps(result['components'])))
    conn.commit()
    conn.close()

    print(f"\n  FIS Composite: {fis_composite:.4f} ({direction})")
    print(f"  ⚠️ 关键：FLOW负 ≠ 财政健康，结构性赤字仍在恶化")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    compute_fis_v2(asof)