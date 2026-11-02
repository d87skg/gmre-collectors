"""engines_v3/defense_v3.py - 传导变量驱动的4道防线（最终修复版）"""
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


def _check_s4_liquidity(conn):
    """直接检查 S4 流动性4条件（避免循环依赖）"""
    conditions = []
    met = 0

    rrp = _load(conn, 'RRP_BALANCE', 30)
    if len(rrp) >= 1:
        rrp_now = float(rrp.iloc[-1])
        ok = rrp_now < 50
        conditions.append(('RRP < $50B', ok, f'RRP={rrp_now:.1f}B'))
        met += ok

    reserve = _load(conn, 'RESERVE_BALANCE', 30)
    if len(reserve) >= 5:
        r_now = float(reserve.iloc[-1])
        r_4w = float(reserve.iloc[-min(4, len(reserve))])
        chg = (r_now - r_4w) / r_4w if r_4w else 0
        ok = chg < 0
        conditions.append(('Reserves ↓ 4W', ok, f'Reserves 4W={chg*100:.2f}%'))
        met += ok

    sofr = _load(conn, 'SOFR', 30)
    effr = _load(conn, 'EFFR', 30)
    if len(sofr) >= 1 and len(effr) >= 1:
        sofr_now = float(sofr.ffill().iloc[-1])
        effr_now = float(effr.ffill().iloc[-1])
        spread_bp = (sofr_now - effr_now) * 100
        ok = spread_bp > 3
        conditions.append(('SOFR-EFFR > +3bp', ok, f'Spread={spread_bp:.2f}bp'))
        met += ok

        vix = _load(conn, 'VIX', 60)
    if len(vix) >= 20:
        vix_vol = float(vix.pct_change().tail(20).std())
        ok = vix_vol > 0.02
        conditions.append(('VIX Dispersion > 2%', ok, f'VIX disp={vix_vol*100:.2f}%'))
        met += ok

    return met, conditions


def evaluate(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        y10 = _load(conn, 'YC10Y', 30)
        wti = _load(conn, 'WTI_OIL', 30)
        ppi = _load(conn, 'PPI', 30)
        usdjpy = _load(conn, 'USD_JPY', 30)
        s4_met, s4_conditions = _check_s4_liquidity(conn)
    finally:
        conn.close()

    lines = []

    # 防线1：滞胀传导
    wti_now = float(wti.iloc[-1]) if len(wti) >= 1 else 0
    ppi_mom = 0
    if len(ppi) >= 2:
        ppi_mom = (float(ppi.iloc[-1]) - float(ppi.iloc[-2])) / float(ppi.iloc[-2])

    d1 = (wti_now > 110) and (ppi_mom > 0.004)
    lines.append({
        'line': '防线1', 'name': 'STAGFLATION_WATCH',
        'triggered': d1,
        'indicator': f'WTI=${wti_now:.1f} PPI MoM={ppi_mom*100:.2f}%',
        'threshold': 'WTI>$110 AND PPI MoM>0.4%',
        'action': '启动滞胀模式：黄金30% + 短债30% + 现金20%'
    })

    # 防线2：利率冲击
    y10_now = float(y10.iloc[-1]) if len(y10) >= 1 else 0
    d2 = y10_now > 5.00
    lines.append({
        'line': '防线2', 'name': 'RATES_STRESS',
        'triggered': d2,
        'indicator': f'10Y={y10_now:.2f}%',
        'threshold': '10Y > 5.00%',
        'action': '降久期：减仓长债+成长股，增配短债'
    })

    # 防线3：流动性紧张（直接计算S4，需≥2项）
    d3 = s4_met >= 2
    lines.append({
        'line': '防线3', 'name': 'LIQUIDITY_STRESS',
        'triggered': d3,
        'indicator': f'S4条件满足 {s4_met}/4',
        'threshold': 'S4触发（≥2项满足）',
        'action': '现金提升至40%+，暂停所有加仓',
        'details': s4_conditions
    })

    # 防线4：Carry Unwind
    usdjpy_now = float(usdjpy.iloc[-1]) if len(usdjpy) >= 1 else 0
    d4 = usdjpy_now < 155.00
    lines.append({
        'line': '防线4', 'name': 'CARRY_UNWIND',
        'triggered': d4,
        'indicator': f'USDJPY={usdjpy_now:.2f}',
        'threshold': 'USDJPY < 155.00',
        'action': '清仓所有杠杆头寸，启动USD/JPY Put'
    })

    triggered = sum(1 for l in lines if l['triggered'])
    result = {
        'asof': asof, 'triggered_count': triggered,
        'overall': f'{triggered}/4 防线突破', 'lines': lines
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS defense_v3 (
            asof_date TEXT PRIMARY KEY,
            triggered_count INTEGER, overall TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO defense_v3
        (asof_date, triggered_count, overall, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, triggered, result['overall'], json.dumps(lines)))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = evaluate(asof)
    print(f"\n{'='*60}")
    print(f"  传导变量防线 - {asof}")
    print(f"{'='*60}")
    print(f"  总体: {result['overall']}\n")
    for l in result['lines']:
        icon = '🚨' if l['triggered'] else '⏸️'
        print(f"  {icon} [{l['line']}] {l['name']}: {l['indicator']}")
        print(f"      阈值: {l['threshold']}")
        print(f"      动作: {l['action']}")
        if 'details' in l:
            for name, ok, val in l['details']:
                mark = '✓' if ok else '✗'
                print(f"        [{mark}] {name}: {val}")
        print()
    print(f"{'='*60}\n")