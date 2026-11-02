"""engines_v3/stress_overlay_v2.py - S0-S8 压力层（审计修正版）"""
import sqlite3
import pandas as pd
import numpy as np
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
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def evaluate_stress(asof: str) -> dict:
    """评估 S0-S8 Stress Overlay（审计修正版）"""
    conn = sqlite3.connect(DB_PATH)
    try:
        y10 = _load(conn, 'YC10Y', 60)
        wti = _load(conn, 'WTI_OIL', 60)
        ppi = _load(conn, 'PPI', 60)
        cpi = _load(conn, 'CPIAUCSL', 60)
        usdjpy = _load(conn, 'USD_JPY', 60)
        vix = _load(conn, 'VIX', 60)
        hyg = _load(conn, 'HY_SPREAD', 60)
        reserve = _load(conn, 'RESERVE_BALANCE', 60)
        sofr = _load(conn, 'SOFR', 60)
        effr = _load(conn, 'EFFR', 60)
        rrp = _load(conn, 'RRP_BALANCE', 60)
        claims = _load(conn, 'JOBLESS_CLAIMS', 60)
        spx = _load(conn, 'SP500', 90)
    finally:
        conn.close()

    layers = []

    # ============ S1 RATES_STRESS ============
    s1_conditions = []
    if len(y10) >= 5:
        y10_now = float(y10.iloc[-1])
        y10_5d_chg = float(y10.iloc[-1] - y10.iloc[-min(5, len(y10))])
        s1_conditions.append(('10Y>5%', y10_now > 5.00, f'{y10_now:.3f}%'))
        s1_conditions.append(('10Y 5D>+15bp', y10_5d_chg > 0.15, f'+{y10_5d_chg*100:.1f}bp'))

    s1_triggered = all(c[1] for c in s1_conditions) if s1_conditions else False
    layers.append({
        'layer': 'S1', 'name': 'RATES_STRESS',
        'triggered': s1_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s1_conditions],
        'description': '利率冲击：10Y突破5% + 速度确认'
    })

    # ============ S2 STAGFLATION_STRESS ============
    s2_conditions = []
    if len(wti) >= 5:
        wti_now = float(wti.iloc[-1])
        s2_conditions.append(('WTI>$105', wti_now > 105, f'${wti_now:.1f}'))
    if len(ppi) >= 2:
        ppi_mom = (float(ppi.iloc[-1]) - float(ppi.iloc[-2])) / float(ppi.iloc[-2]) if float(ppi.iloc[-2]) else 0
        s2_conditions.append(('PPI MoM>0.4%', ppi_mom > 0.004, f'{ppi_mom*100:.2f}%'))

    s2_triggered = sum(1 for c in s2_conditions if c[1]) >= 2
    layers.append({
        'layer': 'S2', 'name': 'STAGFLATION_STRESS',
        'triggered': s2_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s2_conditions],
        'description': f'滞胀压力 ({sum(1 for c in s2_conditions if c[1])}/{len(s2_conditions)}项)'
    })

    # ============ S3 CARRY_STRESS ============
    s3_conditions = []
    if len(usdjpy) >= 21:
        usdjpy_now = float(usdjpy.iloc[-1])
        usdjpy_5d_chg = (float(usdjpy.iloc[-1]) - float(usdjpy.iloc[-min(5, len(usdjpy))])) / float(usdjpy.iloc[-min(5, len(usdjpy))]) if float(usdjpy.iloc[-min(5, len(usdjpy))]) else 0
        usdjpy_vol = float(usdjpy.pct_change().tail(20).std() * (252 ** 0.5))
        s3_conditions.append(('USDJPY 5D<-3%', usdjpy_5d_chg < -0.03, f'{usdjpy_5d_chg*100:.2f}%'))
        s3_conditions.append(('JPY vol>10%', usdjpy_vol > 0.10, f'{usdjpy_vol*100:.1f}%'))

    s3_triggered = sum(1 for c in s3_conditions if c[1]) >= 2
    layers.append({
        'layer': 'S3', 'name': 'CARRY_STRESS',
        'triggered': s3_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s3_conditions],
        'description': f'日元套利压力 ({sum(1 for c in s3_conditions if c[1])}/{len(s3_conditions)}项)'
    })

    # ============ S4 LIQUIDITY_BUFFER_DEPLETION（审计修正：不再是STRESS）============
    s4_conditions = []
    if len(rrp) >= 5:
        rrp_now = float(rrp.iloc[-1])
        s4_conditions.append(('RRP<50B', rrp_now < 50, f'{rrp_now:.1f}B'))

    s4_triggered = sum(1 for c in s4_conditions if c[1]) >= 1
    layers.append({
        'layer': 'S4', 'name': 'LIQUIDITY_BUFFER_DEPLETION',
        'triggered': s4_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s4_conditions],
        'description': '流动性缓冲垫耗尽（非危机，仅缓冲消失）'
    })

    # ============ S5 FUNDING_STRESS（新增，审计要求）============
    s5_conditions = []
    if len(sofr) >= 5 and len(effr) >= 5:
        sofr_now = float(sofr.ffill().iloc[-1])
        effr_now = float(effr.ffill().iloc[-1])
        spread_bp = (sofr_now - effr_now) * 100
        s5_conditions.append(('SOFR-EFFR>+3bp', spread_bp > 3, f'{spread_bp:.2f}bp'))

    if len(reserve) >= 5:
        r_now = float(reserve.iloc[-1])
        r_4w = float(reserve.iloc[-min(4, len(reserve))])
        r_chg = (r_now - r_4w) / r_4w if r_4w else 0
        s5_conditions.append(('Reserves 4W下降', r_chg < 0, f'{r_chg*100:.2f}%'))

    if len(vix) >= 20:
        vix_vol = float(vix.pct_change().tail(20).std())
        s5_conditions.append(('VIX Dispersion>2%', vix_vol > 0.02, f'{vix_vol*100:.2f}%'))

    s5_triggered = sum(1 for c in s5_conditions if c[1]) >= 2
    layers.append({
        'layer': 'S5', 'name': 'FUNDING_STRESS',
        'triggered': s5_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s5_conditions],
        'description': f'融资压力 ({sum(1 for c in s5_conditions if c[1])}/{len(s5_conditions)}项，需≥2)'
    })

    # ============ S6 CREDIT_STRESS（新增）============
    s6_conditions = []
    if len(hyg) >= 20:
        hyg_now = float(hyg.iloc[-1])
        hyg_20d_chg = (hyg_now - float(hyg.iloc[-min(20, len(hyg))])) / float(hyg.iloc[-min(20, len(hyg))]) if float(hyg.iloc[-min(20, len(hyg))]) else 0
        s6_conditions.append(('HY 20D走阔>10%', hyg_20d_chg > 0.10, f'{hyg_20d_chg*100:.2f}%'))
        s6_conditions.append(('HY>3.5', hyg_now > 3.5, f'{hyg_now:.2f}%'))

    s6_triggered = sum(1 for c in s6_conditions if c[1]) >= 1
    layers.append({
        'layer': 'S6', 'name': 'CREDIT_STRESS',
        'triggered': s6_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s6_conditions],
        'description': f'信用压力 ({sum(1 for c in s6_conditions if c[1])}/{len(s6_conditions)}项)'
    })

    # ============ S7 CONTAGION（新增）============
    s7_conditions = []
    if len(spx) >= 30 and len(y10) >= 30:
        spx_ret = spx.pct_change().dropna()
        y10_chg = y10.diff().dropna()
        df = pd.concat([spx_ret.rename('s'), y10_chg.rename('y')], axis=1, sort=True).dropna()
        if len(df) >= 5:
            corr_5d = float(df.tail(5).corr().iloc[0, 1])
            s7_conditions.append(('股债5D相关性>0.5', corr_5d > 0.5, f'{corr_5d:.2f}'))

    s7_triggered = all(c[1] for c in s7_conditions) if s7_conditions else False
    layers.append({
        'layer': 'S7', 'name': 'CONTAGION',
        'triggered': s7_triggered,
        'conditions': [{'name': c[0], 'met': c[1], 'value': c[2]} for c in s7_conditions],
        'description': '传染：跨资产相关性坍塌'
    })

    # ============ S8 SYSTEMIC_CRISIS（需S5+S6+S7同时共振）============
    s5_layer = next((l for l in layers if l['layer'] == 'S5'), None)
    s6_layer = next((l for l in layers if l['layer'] == 'S6'), None)
    s7_layer = next((l for l in layers if l['layer'] == 'S7'), None)

    s8_triggered = (
        (s5_layer and s5_layer['triggered']) and
        (s6_layer and s6_layer['triggered']) and
        (s7_layer and s7_layer['triggered'])
    )
    layers.append({
        'layer': 'S8', 'name': 'SYSTEMIC_CRISIS',
        'triggered': s8_triggered,
        'conditions': [
            {'name': 'S5 FUNDING', 'met': s5_layer['triggered'] if s5_layer else False, 'value': ''},
            {'name': 'S6 CREDIT', 'met': s6_layer['triggered'] if s6_layer else False, 'value': ''},
            {'name': 'S7 CONTAGION', 'met': s7_layer['triggered'] if s7_layer else False, 'value': ''},
        ],
        'description': '系统性危机：S5+S6+S7同时共振'
    })

    # ============ 汇总 ============
    triggered = [l for l in layers if l['triggered'] and l['layer'] not in ['S8']]
    if not triggered:
        overall = 'S0 NORMAL'
    else:
        overall = ' + '.join([l['name'] for l in triggered])

    result = {
        'asof': asof,
        'overall': overall,
        'triggered_count': len(triggered),
        'systemic_confirmed': s8_triggered,
        'layers': layers
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stress_overlay_v2 (
            asof_date TEXT PRIMARY KEY,
            overall TEXT, triggered_count INTEGER, systemic_confirmed INTEGER, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO stress_overlay_v2
        (asof_date, overall, triggered_count, systemic_confirmed, detail)
        VALUES (?, ?, ?, ?, ?)
    """, (asof, overall, len(triggered), int(s8_triggered), json.dumps(layers)))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = evaluate_stress(asof)
    print(f"\n{'='*60}")
    print(f"  Stress Overlay V2 (S0-S8) - {asof}")
    print(f"{'='*60}")
    print(f"  当前状态: {result['overall']}")
    print(f"  已触发层数: {result['triggered_count']}/7")
    print(f"  系统性危机确认: {'🚨 是' if result['systemic_confirmed'] else '🟢 否'}\n")
    for l in result['layers']:
        icon = '🚨' if l['triggered'] else '⏸️'
        print(f"  {icon} [{l['layer']}] {l['name']}")
        print(f"      {l['description']}")
        for c in l['conditions']:
            mark = '✓' if c['met'] else '✗'
            print(f"        [{mark}] {c['name']}: {c['value']}")
    print(f"{'='*60}\n")