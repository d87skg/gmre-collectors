"""engines_v3/shock_engine.py - Shock Engine (7类冲击)"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=60):
    for col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {col} AS dt, value FROM observations WHERE series_id=? ORDER BY {col} DESC LIMIT ?",
                conn, params=(sid, limit)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def _scale(v, lo, hi):
    if v is None or pd.isna(v):
        return 0.0
    return float(np.clip((v - lo) / (hi - lo), 0, 1))


def _stats(series, window=5):
    """返回变化率、速度、持续性"""
    if len(series) < window + 1:
        return 0, 0, 0
    s = series.dropna()
    chg = float(s.iloc[-1] - s.iloc[-window]) / abs(s.iloc[-window]) if s.iloc[-window] else 0
    v1 = float(s.iloc[-1] - s.iloc[-2]) if len(s) >= 2 else 0
    v5 = chg
    # 持续性：5日变化方向一致的比例
    diffs = s.diff().tail(window).dropna()
    persist = abs(diffs.sum()) / (diffs.abs().sum() + 1e-9) if len(diffs) > 0 else 0
    return chg, v5, persist


def detect_supply_shock(conn):
    """供给冲击：油价"""
    wti = _load(conn, 'WTI_OIL', 60)
    brent = _load(conn, 'BRENT_OIL', 60)
    if len(wti) < 6:
        return 0, 0, 0
    chg5, _, persist = _stats(wti, 5)
    intensity = _scale(chg5, 0.02, 0.15)
    velocity = _scale(chg5, 0.01, 0.08)
    return intensity, velocity, persist


def detect_policy_shock(conn):
    """政策冲击：2Y收益率快速重定价"""
    y2 = _load(conn, 'YC2Y', 30)
    if len(y2) < 6:
        return 0, 0, 0
    chg5_bp = float(y2.iloc[-1] - y2.iloc[-6]) * 100
    intensity = _scale(abs(chg5_bp), 10, 50)
    velocity = _scale(abs(chg5_bp), 5, 30)
    _, _, persist = _stats(y2, 5)
    return intensity, velocity, persist


def detect_fiscal_shock(conn):
    """财政冲击：长端利率"""
    y30 = _load(conn, 'YC30Y', 30)
    y10 = _load(conn, 'YC10Y', 30)
    if len(y30) < 6 or len(y10) < 6:
        return 0, 0, 0
    chg30 = float(y30.iloc[-1] - y30.iloc[-6]) * 100
    curve = float(y30.iloc[-1] - y10.iloc[-1]) * 100
    intensity = _scale(chg30 + curve * 0.5, 5, 40)
    velocity = _scale(chg30, 3, 25)
    _, _, persist = _stats(y30, 5)
    return intensity, velocity, persist


def detect_financial_shock(conn):
    """金融冲击：VIX + HY"""
    vix = _load(conn, 'VIX', 30)
    hyg = _load(conn, 'HY_SPREAD', 30)
    if len(vix) < 6:
        return 0, 0, 0
    chg_vix = float(vix.iloc[-1] - vix.iloc[-6]) / float(vix.iloc[-6]) if float(vix.iloc[-6]) else 0
    chg_hyg = 0
    if len(hyg) >= 6:
        chg_hyg = float(hyg.iloc[-1] - hyg.iloc[-6])
    intensity = _scale(chg_vix * 100 + chg_hyg * 5, 5, 50)
    velocity = _scale(chg_vix * 100, 3, 30)
    _, _, persist = _stats(vix, 5)
    return intensity, velocity, persist


def detect_demand_shock(conn):
    """需求冲击：就业 + 消费"""
    claims = _load(conn, 'JOBLESS_CLAIMS', 30)
    unrate = _load(conn, 'UNEMPLOYMENT', 30)
    if len(claims) < 6:
        return 0, 0, 0
    chg = float(claims.iloc[-1] - claims.iloc[-6]) / float(claims.iloc[-6]) if float(claims.iloc[-6]) else 0
    intensity = _scale(chg, 0.02, 0.15)
    velocity = _scale(chg, 0.01, 0.10)
    _, _, persist = _stats(claims, 5)
    return intensity, velocity, persist


def detect_liquidity_shock(conn):
    """流动性冲击：RRP + SOFR"""
    rrp = _load(conn, 'RRP_BALANCE', 30)
    sofr = _load(conn, 'SOFR', 30)
    effr = _load(conn, 'EFFR', 30)
    if len(sofr) < 6 or len(effr) < 6:
        return 0, 0, 0
    spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
    rrp_low = 1.0 if (len(rrp) > 0 and float(rrp.iloc[-1]) < 100) else 0.0
    intensity = _scale(spread + rrp_low * 30, 0, 40)
    velocity = _scale(spread, 0, 15)
    _, _, persist = _stats(sofr, 5)
    return intensity, velocity, persist


def detect_geopolitical_shock(conn):
    """地缘冲击：油价+VIX共振"""
    wti = _load(conn, 'WTI_OIL', 30)
    vix = _load(conn, 'VIX', 30)
    if len(wti) < 6 or len(vix) < 6:
        return 0, 0, 0
    chg_oil = float(wti.iloc[-1] - wti.iloc[-6]) / float(wti.iloc[-6]) if float(wti.iloc[-6]) else 0
    chg_vix = float(vix.iloc[-1] - vix.iloc[-6]) / float(vix.iloc[-6]) if float(vix.iloc[-6]) else 0
    # 两者同步上涨 = 地缘冲击
    if chg_oil > 0 and chg_vix > 0:
        intensity = _scale(chg_oil * 50 + chg_vix * 50, 5, 40)
    else:
        intensity = 0.0
    velocity = _scale(chg_oil * 100, 3, 20)
    _, _, persist = _stats(wti, 5)
    return intensity, velocity, persist


SHOCKS = [
    ('SUPPLY',        detect_supply_shock),
    ('POLICY',        detect_policy_shock),
    ('FISCAL',        detect_fiscal_shock),
    ('FINANCIAL',     detect_financial_shock),
    ('DEMAND',        detect_demand_shock),
    ('LIQUIDITY',     detect_liquidity_shock),
    ('GEOPOLITICAL',  detect_geopolitical_shock),
]


def compute_shock(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    results = []
    try:
        for name, fn in SHOCKS:
            try:
                i, v, p = fn(conn)
                confidence = 0.85 if i > 0.5 else 0.7
                results.append({
                    'shock_type': name,
                    'intensity': round(i, 3),
                    'velocity': round(v, 3),
                    'persistence': round(p, 3),
                    'confidence': confidence
                })
            except Exception as e:
                results.append({
                    'shock_type': name, 'intensity': 0, 'velocity': 0,
                    'persistence': 0, 'error': str(e)[:60]
                })
    finally:
        conn.close()

    # 排序
    results_sorted = sorted(results, key=lambda x: x['intensity'], reverse=True)
    primary = results_sorted[0]
    secondary = results_sorted[1] if len(results_sorted) > 1 else None

    output = {
        'asof': asof,
        'primary_shock': primary['shock_type'] if primary['intensity'] > 0.3 else 'NONE',
        'primary_intensity': primary['intensity'],
        'secondary_shock': secondary['shock_type'] if secondary and secondary['intensity'] > 0.2 else 'NONE',
        'secondary_intensity': secondary['intensity'] if secondary else 0,
        'all_shocks': results_sorted
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS shock_engine (
        asof_date TEXT PRIMARY KEY, primary_shock TEXT, primary_intensity REAL,
        secondary_shock TEXT, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO shock_engine
        (asof_date, primary_shock, primary_intensity, secondary_shock, detail)
        VALUES (?, ?, ?, ?, ?)""",
        (asof, output['primary_shock'], primary['intensity'],
         output['secondary_shock'], json.dumps(results_sorted)))
    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  Shock Engine - {asof}")
    print(f"{'='*60}")
    print(f"  Primary:   {output['primary_shock']} (intensity={primary['intensity']:.3f})")
    print(f"  Secondary: {output['secondary_shock']} (intensity={secondary['intensity']:.3f})" if secondary else "  Secondary: NONE")
    print(f"\n  所有冲击:")
    for r in results_sorted:
        bar = '#' * int(r['intensity'] * 30)
        print(f"    {r['shock_type']:14s} I={r['intensity']:.3f} V={r['velocity']:.3f} P={r['persistence']:.3f} {bar}")
    print(f"{'='*60}\n")

    return output


if __name__ == "__main__":
    compute_shock(datetime.now().strftime('%Y-%m-%d'))