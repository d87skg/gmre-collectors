"""engines_v2/yen_carry_state.py - 日元套利去杠杆状态机（真实数据版）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load_series(conn, sid, lookback=180):
    for date_col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {date_col} AS dt, value FROM observations "
                f"WHERE series_id=? ORDER BY {date_col} DESC LIMIT ?",
                conn, params=(sid, lookback)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value']
        except Exception:
            continue
    return pd.Series(dtype=float)


def update_state(asof: str) -> dict:
    """
    日元套利状态机（真实数据驱动）
    输入：USD/JPY 汇率 + 日本10Y国债 + 美日利差 + VIX + DXY
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        usdjpy = _load_series(conn, 'USD_JPY', 180)
        jp10y  = _load_series(conn, 'JP_10Y_YIELD', 180)
        us10y  = _load_series(conn, 'YC10Y', 180)
        vix    = _load_series(conn, 'VIX', 180)
        dxy    = _load_series(conn, 'DXY_PROXY', 180)
    finally:
        conn.close()

    # 数据充足性判断
    if len(usdjpy) < 20:
        result = {'state': 'NORMAL', 'risk_budget_adj': 1.0,
                  'hedge_action': 'NONE', 'error': 'insufficient_usdjpy_data'}
        _save_state(asof, result)
        return result

    # 计算核心指标
    usdjpy_now = float(usdjpy.iloc[-1])
    usdjpy_20d_chg = float((usdjpy.iloc[-1] - usdjpy.iloc[-min(20, len(usdjpy))]) / usdjpy.iloc[-min(20, len(usdjpy))])

    # JPY波动率（20日标准差，年化）
    jpy_returns = usdjpy.pct_change().dropna()
    jpy_vol = float(jpy_returns.tail(20).std() * np.sqrt(252))

    # 美日利差（bp）
    spread = 0.0
    if len(us10y) >= 5 and len(jp10y) >= 5:
        us10y_now = float(us10y.ffill().iloc[-1])
        jp10y_now = float(jp10y.ffill().iloc[-1])
        spread = (us10y_now - jp10y_now) * 100  # bp

    # VIX变化
    vix_20d_chg = 0.0
    if len(vix) >= 20:
        vix_now = float(vix.iloc[-1])
        vix_20d_ago = float(vix.iloc[-min(20, len(vix))])
        vix_20d_chg = (vix_now - vix_20d_ago) / vix_20d_ago if vix_20d_ago > 0 else 0

    # DXY变化
    dxy_20d_chg = 0.0
    if len(dxy) >= 20:
        dxy_now = float(dxy.iloc[-1])
        dxy_20d_ago = float(dxy.iloc[-min(20, len(dxy))])
        dxy_20d_chg = (dxy_now - dxy_20d_ago) / dxy_20d_ago if dxy_20d_ago > 0 else 0

    # ============ 状态判定逻辑 ============
    # 核心信号：日元急升（USDJPY下跌）+ 波动率抬升 + 美日利差收缩
    state = 'NORMAL'
    adj, action = 1.0, 'NONE'

    # SYSTEMIC_DELEVERAGING：日元急升>4% + 波动率>15% + VIX大幅抬升
    if usdjpy_20d_chg < -0.04 and jpy_vol > 0.15 and vix_20d_chg > 0.3:
        state = 'SYSTEMIC_DELEVERAGING'
        adj, action = 0.0, 'CIRCUIT_BREAKER_CASH'
    # CARRY_UNWIND：日元升>3% + 波动率>10%
    elif usdjpy_20d_chg < -0.03 and jpy_vol > 0.10:
        state = 'CARRY_UNWIND'
        adj, action = 0.60, 'FORCE_REDUCE_HIGH_BETA'
    # CARRY_STRESS：日元升>2% + 波动率>8%
    elif usdjpy_20d_chg < -0.02 and jpy_vol > 0.08:
        state = 'CARRY_STRESS'
        adj, action = 0.85, 'ENABLE_TAIL_HEDGE'
    # CARRY_WARNING：日元升>1% 或 波动率>6%
    elif usdjpy_20d_chg < -0.01 or jpy_vol > 0.06:
        state = 'CARRY_WARNING'
        adj, action = 0.95, 'MONITOR'

    result = {
        'state': state,
        'risk_budget_adj': adj,
        'hedge_action': action,
        'metrics': {
            'usdjpy': round(usdjpy_now, 2),
            'usdjpy_20d_chg_pct': round(usdjpy_20d_chg * 100, 2),
            'jpy_vol_annualized': round(jpy_vol * 100, 2),
            'us_jp_spread_bp': round(spread, 1),
            'vix_20d_chg_pct': round(vix_20d_chg * 100, 2),
            'dxy_20d_chg_pct': round(dxy_20d_chg * 100, 2),
        }
    }

    _save_state(asof, result)
    return result


def _save_state(asof: str, result: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tail_states (
            asof_date TEXT PRIMARY KEY,
            state TEXT, risk_budget_adj REAL, hedge_action TEXT, metrics TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO tail_states
        (asof_date, state, risk_budget_adj, hedge_action, metrics)
        VALUES (?, ?, ?, ?, ?)
    """, (asof, result['state'], result['risk_budget_adj'],
          result['hedge_action'], json.dumps(result.get('metrics', {}))))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = update_state(asof)
    print(f"\n{'='*60}")
    print(f"  日元套利状态机 - {asof}")
    print(f"{'='*60}")
    print(f"  状态: {result['state']}")
    print(f"  风险预算: {result['risk_budget_adj']*100:.0f}%")
    print(f"  对冲动作: {result['hedge_action']}")
    if 'metrics' in result:
        print(f"\n  关键指标:")
        for k, v in result['metrics'].items():
            print(f"    {k}: {v}")
    print(f"{'='*60}\n")