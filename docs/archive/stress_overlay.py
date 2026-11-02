"""engines_v3/stress_overlay.py - Stress Overlay S0-S5（传导链视角）"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load(conn, sid, limit=60):
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


def evaluate_stress(asof: str) -> dict:
    """评估 S0-S5 Stress Overlay"""
    conn = sqlite3.connect(DB_PATH)
    try:
        y10     = _load(conn, 'YC10Y', 60)
        move    = _load(conn, 'MOVE', 60)
        wti     = _load(conn, 'WTI_OIL', 60)
        ppi     = _load(conn, 'PPI', 60)
        cpi     = _load(conn, 'CPIAUCSL', 60)
        usdjpy  = _load(conn, 'USD_JPY', 60)
        jp10y   = _load(conn, 'JP_10Y_YIELD', 60)
        vix     = _load(conn, 'VIX', 60)
        hyg     = _load(conn, 'HY_SPREAD', 60)
        reserve = _load(conn, 'RESERVE_BALANCE', 60)
        sofr    = _load(conn, 'SOFR', 60)
        effr    = _load(conn, 'EFFR', 60)
        rrp     = _load(conn, 'RRP_BALANCE', 60)
        payroll = _load(conn, 'PAYROLLS', 60)
        claims  = _load(conn, 'JOBLESS_CLAIMS', 60)
    finally:
        conn.close()

    layers = []

    # ============ S1: RATES_STRESS ============
    s1_conditions = []
    if len(y10) >= 5:
        y10_now = float(y10.iloc[-1])
        s1_conditions.append(('10Y > 5%', y10_now > 5.00, f'10Y={y10_now:.2f}%'))
    if len(move) >= 5:
        move_now = float(move.iloc[-1])
        move_20d_chg = (move_now - float(move.iloc[-min(20, len(move))])) / float(move.iloc[-min(20, len(move))])
        s1_conditions.append(('MOVE > +15%', move_20d_chg > 0.15, f'MOVE 20d={move_20d_chg*100:.1f}%'))

    s1_triggered = all(c[1] for c in s1_conditions) if s1_conditions else False
    layers.append({
        'layer': 'S1', 'name': 'RATES_STRESS',
        'triggered': s1_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s1_conditions],
        'description': '利率冲击：长端收益率突破关键位 + 债市波动率抬升'
    })

    # ============ S2: STAGFLATION_STRESS ============
    s2_conditions = []
    if len(wti) >= 5:
        wti_now = float(wti.iloc[-1])
        s2_conditions.append(('WTI > $110', wti_now > 110, f'WTI=${wti_now:.1f}'))
    if len(ppi) >= 5:
        ppi_now = float(ppi.iloc[-1])
        ppi_prev = float(ppi.iloc[-2]) if len(ppi) >= 2 else ppi_now
        ppi_mom = (ppi_now - ppi_prev) / ppi_prev if ppi_prev else 0
        s2_conditions.append(('PPI MoM > 0.4%', ppi_mom > 0.004, f'PPI MoM={ppi_mom*100:.2f}%'))

    # 至少满足2项
    met_count = sum(1 for c in s2_conditions if c[1])
    s2_triggered = met_count >= 2
    layers.append({
        'layer': 'S2', 'name': 'STAGFLATION_STRESS',
        'triggered': s2_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s2_conditions],
        'description': f'滞胀压力：能源冲击 + 上游通胀传导 ({met_count}/{len(s2_conditions)}项满足)'
    })

    # ============ S3: CARRY_STRESS ============
    s3_conditions = []
    if len(usdjpy) >= 21:
        usdjpy_now = float(usdjpy.iloc[-1])
        usdjpy_5d = float(usdjpy.iloc[-min(5, len(usdjpy))])
        usdjpy_5d_chg = (usdjpy_now - usdjpy_5d) / usdjpy_5d if usdjpy_5d else 0
        usdjpy_vol = float(usdjpy.pct_change().tail(20).std() * (252 ** 0.5))

        s3_conditions.append(('USDJPY < 155', usdjpy_now < 155, f'USDJPY={usdjpy_now:.2f}'))
        s3_conditions.append(('JPY vol > 10%', usdjpy_vol > 0.10, f'JPY vol={usdjpy_vol*100:.1f}%'))
        s3_conditions.append(('JPY 5D return < -3%', usdjpy_5d_chg < -0.03, f'JPY 5D={usdjpy_5d_chg*100:.2f}%'))

    met_count = sum(1 for c in s3_conditions if c[1])
    s3_triggered = met_count >= 2
    layers.append({
        'layer': 'S3', 'name': 'CARRY_STRESS',
        'triggered': s3_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s3_conditions],
        'description': f'日元套利平仓压力 ({met_count}/{len(s3_conditions)}项满足)'
    })

    # ============ S4: LIQUIDITY_STRESS ============
    s4_conditions = []
    if len(rrp) >= 5:
        rrp_now = float(rrp.iloc[-1])
        s4_conditions.append(('RRP < $50B', rrp_now < 50, f'RRP={rrp_now:.1f}B'))

    if len(reserve) >= 5:
        reserve_now = float(reserve.iloc[-1])
        reserve_4w = float(reserve.iloc[-min(4, len(reserve))])
        reserve_4w_chg = (reserve_now - reserve_4w) / reserve_4w if reserve_4w else 0
        s4_conditions.append(('Reserves ↓ 4W', reserve_4w_chg < 0, f'Reserves 4W={reserve_4w_chg*100:.2f}%'))

    if len(sofr) >= 5 and len(effr) >= 5:
        sofr_now = float(sofr.ffill().iloc[-1])
        effr_now = float(effr.ffill().iloc[-1])
        spread_bp = (sofr_now - effr_now) * 100
        s4_conditions.append(('SOFR-EFFR > +3bp', spread_bp > 3, f'Spread={spread_bp:.2f}bp'))

    if len(vix) >= 20:
        vix_vol = float(vix.pct_change().tail(20).std())
        s4_conditions.append(('Repo Dispersion > 2%', vix_vol > 0.02, f'VIX disp={vix_vol*100:.2f}%'))

    met_count = sum(1 for c in s4_conditions if c[1])
    # S4需要至少2项满足（避免RRP单独触发）
    s4_triggered = met_count >= 2
    layers.append({
        'layer': 'S4', 'name': 'LIQUIDITY_STRESS',
        'triggered': s4_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],
        'description': f'流动性紧张 ({met_count}/{len(s4_conditions)}项满足，需≥2)'
    })

    # ============ S5: SYSTEMIC_STRESS ============
    s5_conditions = []
    if len(hyg) >= 5:
        hyg_now = float(hyg.iloc[-1])
        hyg_20d = float(hyg.iloc[-min(20, len(hyg))])
        hyg_chg = (hyg_now - hyg_20d) / hyg_20d if hyg_20d else 0
        s5_conditions.append(('HY Spread ↑ 20%', hyg_chg > 0.20, f'HY={hyg_now:.2f}%'))

    if len(claims) >= 5:
        claims_now = float(claims.iloc[-1])
        claims_4w = float(claims.iloc[-min(4, len(claims))])
        claims_chg = (claims_now - claims_4w) / claims_4w if claims_4w else 0
        s5_conditions.append(('Claims ↑ 10%', claims_chg > 0.10, f'Claims={claims_now:,.0f}'))

    if len(vix) >= 20:
        vix_now = float(vix.iloc[-1])
        vix_20d = float(vix.iloc[-min(20, len(vix))])
        vix_chg = (vix_now - vix_20d) / vix_20d if vix_20d else 0
        s5_conditions.append(('VIX ↑ 30%', vix_chg > 0.30, f'VIX={vix_now:.2f}'))

    met_count = sum(1 for c in s5_conditions if c[1])
    s5_triggered = met_count >= 2
    layers.append({
        'layer': 'S5', 'name': 'SYSTEMIC_STRESS',
        'triggered': s5_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s5_conditions],
        'description': f'系统性危机预警 ({met_count}/{len(s5_conditions)}项满足，需≥2)'
    })

    # ============ 汇总 ============
    triggered_layers = [l for l in layers if l['triggered']]
    if not triggered_layers:
        overall = 'S0 NORMAL'
    else:
        overall = ' + '.join([l['name'] for l in triggered_layers])

    result = {
        'asof': asof,
        'overall': overall,
        'triggered_count': len(triggered_layers),
        'layers': layers
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stress_overlay (
            asof_date TEXT PRIMARY KEY,
            overall TEXT, triggered_count INTEGER, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO stress_overlay
        (asof_date, overall, triggered_count, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, overall, len(triggered_layers), json.dumps(layers)))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = evaluate_stress(asof)
    print(f"\n{'='*60}")
    print(f"  Stress Overlay 压力叠加层 - {asof}")
    print(f"{'='*60}")
    print(f"  当前状态: {result['overall']}")
    print(f"  已触发层数: {result['triggered_count']}/5\n")
    for l in result['layers']:
        icon = '🚨' if l['triggered'] else '⏸️'
        print(f"  {icon} [{l['layer']}] {l['name']}")
        print(f"      {l['description']}")
        for c in l['conditions']:
            mark = '✓' if c['met'] else '✗'
            print(f"        [{mark}] {c['name']}: {c['value']}")
        print()
    print(f"{'='*60}\n")