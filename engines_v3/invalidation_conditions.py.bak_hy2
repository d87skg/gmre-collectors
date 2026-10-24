"""engines_v3/invalidation_conditions.py - 判断失效条件（审计新增）"""
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
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def check_invalidation(asof: str) -> dict:
    """检查看空/防御判断是否失效"""
    print(f"\n{'='*60}")
    print(f"  判断失效条件检查 - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        wti = _load(conn, 'WTI_OIL', 30)
        y10 = _load(conn, 'YC10Y', 30)
        usdjpy = _load(conn, 'USD_JPY', 30)
        sofr = _load(conn, 'SOFR', 30)
        effr = _load(conn, 'EFFR', 30)
        hyg = _load(conn, 'HY_SPREAD', 30)
    finally:
        conn.close()

    # 6个失效条件
    conditions = []

    # 1. Oil < $95
    if len(wti) >= 1:
        wti_now = float(wti.iloc[-1])
        conditions.append({
            'name': 'Oil < $95',
            'met': wti_now < 95,
            'value': f'${wti_now:.1f}'
        })

    # 2. 10Y < 4.75%
    if len(y10) >= 1:
        y10_now = float(y10.iloc[-1])
        conditions.append({
            'name': '10Y < 4.75%',
            'met': y10_now < 4.75,
            'value': f'{y10_now:.3f}%'
        })

    # 3. USDJPY稳定（20日变化 < 1%）
    if len(usdjpy) >= 21:
        usdjpy_now = float(usdjpy.iloc[-1])
        usdjpy_20d_chg = abs((usdjpy_now - float(usdjpy.iloc[-min(20, len(usdjpy))])) / float(usdjpy.iloc[-min(20, len(usdjpy))]))
        conditions.append({
            'name': 'USDJPY稳定（20D<1%）',
            'met': usdjpy_20d_chg < 0.01,
            'value': f'{usdjpy_20d_chg*100:.2f}%'
        })

    # 4. SOFR-EFFR正常
    if len(sofr) >= 1 and len(effr) >= 1:
        spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
        conditions.append({
            'name': 'SOFR-EFFR < +3bp',
            'met': spread < 3,
            'value': f'{spread:.2f}bp'
        })

    # 5. HY利差稳定（20日变化 < 10%）
    if len(hyg) >= 21:
        hyg_now = float(hyg.iloc[-1])
        hyg_20d_chg = abs((hyg_now - float(hyg.iloc[-min(20, len(hyg))])) / float(hyg.iloc[-min(20, len(hyg))]))
        conditions.append({
            'name': 'HY利差稳定（20D<10%）',
            'met': hyg_20d_chg < 0.10,
            'value': f'{hyg_20d_chg*100:.2f}%'
        })

    # 6. 通胀预期回落（占位，等INF_EXPECT引擎）
    conditions.append({
        'name': '通胀预期回落（待实现）',
        'met': False,
        'value': 'N/A'
    })

    # 汇总
    met_count = sum(1 for c in conditions if c['met'])
    total = len(conditions)

    if met_count >= 5:
        status = 'INVALIDATED'  # 判断失效
        msg = f'🔓 看空判断失效（{met_count}/{total}满足）：市场已normalize'
    elif met_count >= 3:
        status = 'WEAKENING'
        msg = f'🟡 看空判断减弱（{met_count}/{total}满足）'
    else:
        status = 'ACTIVE'
        msg = f'🔴 看空判断仍有效（{met_count}/{total}满足）'

    print(f"  {msg}\n")
    for c in conditions:
        mark = '✓' if c['met'] else '✗'
        print(f"    [{mark}] {c['name']}: {c['value']}")

    result = {
        'asof': asof,
        'status': status,
        'met_count': met_count,
        'total_count': total,
        'conditions': conditions
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invalidation_conditions (
            asof_date TEXT PRIMARY KEY,
            status TEXT, met_count INTEGER, total_count INTEGER, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO invalidation_conditions
        (asof_date, status, met_count, total_count, detail)
        VALUES (?, ?, ?, ?, ?)
    """, (asof, status, met_count, total, json.dumps(conditions)))
    conn.commit()
    conn.close()

    print(f"{'='*60}\n")
    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    check_invalidation(asof)