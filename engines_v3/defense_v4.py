"""engines_v3/defense_v4.py - 防线0-7（v4.2: 时区统一 + asof 可复现 + HY Fail-Closed）"""
import sys as _sys
from pathlib import Path as _Path
_PROJECT_ROOT = _Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_PROJECT_ROOT))

from tools.rrp_guard import run_rrp_guard, DownstreamAction, RRPStatus
import sqlite3
import pandas as pd
import json
from datetime import datetime

import os
DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

from core import data_proxy


def _load(conn, sid, limit=60, asof=None):
    return data_proxy.load_for_engine(
        conn, sid, limit, as_index='datetime', asof=asof
    )


def _days_since(latest_date, asof_str):
    """返回 latest_date 到 asof_str 的自然日差。
    统一处理 tz-aware / tz-naive 两种 Timestamp，避免 .tz_localize(None) 对 naive 抛错。
    """
    try:
        ts = pd.Timestamp(latest_date)
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        asof_dt = pd.Timestamp(asof_str)
        if asof_dt.tz is not None:
            asof_dt = asof_dt.tz_localize(None)
        return int((asof_dt - ts).days)
    except Exception:
        return None


def evaluate_v4(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Defense V4 (防线0-7) - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        wti = _load(conn, 'WTI_OIL', 30, asof=asof)
        mich = _load(conn, 'MICH_1Y_EXPECT', 30, asof=asof)
        yc2y = _load(conn, 'YC2Y', 30, asof=asof)
        y10 = _load(conn, 'YC10Y', 30, asof=asof)
        sofr = _load(conn, 'SOFR', 30, asof=asof)
        effr = _load(conn, 'EFFR', 30, asof=asof)
        # 走别名链：HY_OAS → HY_SPREAD（与全局数据资格口径一致）
        hyg = _load(conn, 'HY_OAS', 30, asof=asof)
        spx = _load(conn, 'SP500', 60, asof=asof)
    finally:
        conn.close()

    lines = []

    # ============ 防线0：INFLATION_SHOCK ============
    d0_conds = []
    if len(wti) >= 1:
        d0_conds.append(('WTI>$105', float(wti.iloc[-1]) > 105, f'${float(wti.iloc[-1]):.1f}'))

    # 强制校验 MICH 新鲜度（asof 对齐，时区统一）
    mich_valid = False
    mich_reason = 'MISSING'
    if len(mich) >= 1:
        lag = _days_since(mich.index[-1], asof)
        if lag is not None and lag <= 45:
            mich_valid = True
            mich_reason = f'OK (lag={lag}d)'
        elif lag is not None:
            mich_reason = f'STALE (lag={lag}d > 45d)'

    if mich_valid:
        d0_conds.append(('通胀预期>4.0%', float(mich.iloc[-1]) > 4.0,
                         f'{float(mich.iloc[-1]):.2f}%'))
    else:
        d0_conds.append(('通胀预期>4.0%', False, f'[✗] {mich_reason}'))

    d0 = sum(1 for c in d0_conds if c[1]) >= 2
    lines.append({
        'line': '防线0', 'name': 'INFLATION_SHOCK',
        'triggered': d0, 'conditions': d0_conds,
        'action': '增配黄金+短债，避免长端'
    })

    # ============ 防线1：POLICY_SHOCK ============
    d1_conds = []
    if len(yc2y) >= 6:
        y2_5d = (float(yc2y.iloc[-1]) - float(yc2y.iloc[-min(5, len(yc2y))])) * 100
        d1_conds.append(('2Y 5D>+15bp', y2_5d > 15, f'+{y2_5d:.1f}bp'))
    d1 = sum(1 for c in d1_conds if c[1]) >= 1
    lines.append({
        'line': '防线1', 'name': 'POLICY_SHOCK',
        'triggered': d1, 'conditions': d1_conds,
        'action': '政策重定价中，降久期'
    })

    # ============ 防线2：RATES_SHOCK ============
    d2_conds = []
    if len(y10) >= 1:
        d2_conds.append(('10Y>5%', float(y10.iloc[-1]) > 5.00, f'{float(y10.iloc[-1]):.3f}%'))
    d2 = sum(1 for c in d2_conds if c[1]) >= 1
    lines.append({
        'line': '防线2', 'name': 'RATES_SHOCK',
        'triggered': d2, 'conditions': d2_conds,
        'action': '降久期，减仓长债+成长股'
    })

    # ============ 防线3：LIQUIDITY_BUFFER_DEPLETION ============
    d3_conds = []
    try:
        _g3 = run_rrp_guard(verbose=False)
        if _g3.downstream_action in (DownstreamAction.BLOCK, DownstreamAction.OBSERVE):
            d3_conds.append(('RRP_DATA_CRITICAL', True, f"数据源异常: {_g3.status.value}"))
            d3 = True
            print(f"🚨 [FAIL-CLOSED] 防线3强制触发：RRP 数据不可靠 ({_g3.status.value})")
        elif _g3.primary_value is not None:
            _rrp_used = float(_g3.primary_value)
            _rrp_src = _g3.primary_source
            d3_conds.append((f'RRP<50B ({_rrp_src})', _rrp_used < 50, f'{_rrp_used:.2f}B'))
            d3 = sum(1 for c in d3_conds if c[1]) >= 1
        else:
            d3_conds.append(('RRP_NONE', True, "无主源数据"))
            d3 = True
    except Exception as _e:
        d3_conds.append(('RRP_GUARD_ERROR', True, str(_e)[:50]))
        d3 = True
        print(f"🚨 [FAIL-CLOSED] 防线3强制触发：RRP Guard 调用崩溃 ({_e})")

    lines.append({
        'line': '防线3', 'name': 'LIQUIDITY_BUFFER',
        'triggered': d3, 'conditions': d3_conds,
        'action': '流动性缓冲耗尽或数据盲区，强制提升现金至40%+'
    })

    # ============ 防线4：FUNDING_STRESS ============
    d4_conds = []
    d4 = False
    sofr_valid = len(sofr) >= 1
    effr_valid = len(effr) >= 1

    if not sofr_valid or not effr_valid:
        d4_conds.append(('SOFR/EFFR_DATA_MISSING', True, '数据缺失'))
        d4 = True
        print("🚨 [FAIL-CLOSED] 防线4强制触发：SOFR/EFFR 数据缺失")
    else:
        # 时区统一 + asof 对齐
        lag = _days_since(sofr.index[-1], asof)
        if lag is not None and lag > 3:
            d4_conds.append(('SOFR_DATA_STALE', True, f'滞后 {lag} 天'))
            d4 = True
            print(f"🚨 [FAIL-CLOSED] 防线4强制触发：SOFR 数据过期 (滞后 {lag} 天)")

        if not d4:
            spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
            d4_conds.append(('SOFR-EFFR>+3bp', spread > 3, f'{spread:.2f}bp'))
            d4 = sum(1 for c in d4_conds if c[1]) >= 1

    lines.append({
        'line': '防线4', 'name': 'FUNDING_STRESS',
        'triggered': d4, 'conditions': d4_conds,
        'action': '融资压力确认或数据盲区，全面防御降杠杆'
    })

    # ============ 防线5：CREDIT_STRESS ============
    d5_conds = []
    d5 = False

    if len(hyg) == 0:
        # Fail-Closed：HY 完全缺失时，宁可报信用风险，不静默漏报
        d5_conds.append(('HY_DATA_MISSING', True, '数据完全缺失'))
        d5 = True
        print("🚨 [FAIL-CLOSED] 防线5强制触发：HY 信用利差数据完全缺失")
    elif len(hyg) >= 20:
        hyg_now = float(hyg.iloc[-1])
        hyg_20d = float(hyg.iloc[-min(20, len(hyg))])
        hyg_20d_chg = (hyg_now - hyg_20d) / hyg_20d if hyg_20d else 0
        _hy_dir = '走阔' if hyg_20d_chg > 0 else '收窄'
        d5_conds.append((f'HY 20D{_hy_dir}>10%', hyg_20d_chg > 0.10, f'{hyg_20d_chg*100:+.2f}%'))
        d5 = sum(1 for c in d5_conds if c[1]) >= 1
    else:
        # 数据不足 20 条但 > 0：不误用数据，但也不 Fail-Closed（数据不足以判断）
        d5_conds.append(('HY_SAMPLE_INSUFFICIENT', False, f'仅 {len(hyg)} 条，需 20 条'))

    lines.append({
        'line': '防线5', 'name': 'CREDIT_STRESS',
        'triggered': d5, 'conditions': d5_conds,
        'action': '信用压力确认，清仓高Beta'
    })

    # ============ 防线6：CONTAGION ============
    d6_conds = []
    if len(spx) >= 30 and len(y10) >= 30:
        spx_ret = spx.pct_change().dropna()
        y10_chg = y10.diff().dropna()
        df = pd.concat(
            [spx_ret.rename('s'), y10_chg.rename('y')],
            axis=1
        ).dropna()
        if len(df) >= 5:
            corr5 = float(df.tail(5).corr().iloc[0, 1])
            d6_conds.append(('股债5D>0.5', corr5 > 0.5, f'{corr5:.2f}'))
    d6 = sum(1 for c in d6_conds if c[1]) >= 1
    lines.append({
        'line': '防线6', 'name': 'CONTAGION',
        'triggered': d6, 'conditions': d6_conds,
        'action': '传染确认，全面去杠杆'
    })

    # ============ 防线7：SYSTEMIC ============
    d4_layer = next((l for l in lines if l['line'] == '防线4'), None)
    d5_layer = next((l for l in lines if l['line'] == '防线5'), None)
    d6_layer = next((l for l in lines if l['line'] == '防线6'), None)

    d7 = bool(
        d4_layer and d4_layer['triggered'] and
        d5_layer and d5_layer['triggered'] and
        d6_layer and d6_layer['triggered']
    )
    lines.append({
        'line': '防线7', 'name': 'SYSTEMIC',
        'triggered': d7,
        'conditions': [
            ('防线4 FUNDING', d4_layer['triggered'] if d4_layer else False, ''),
            ('防线5 CREDIT', d5_layer['triggered'] if d5_layer else False, ''),
            ('防线6 CONTAGION', d6_layer['triggered'] if d6_layer else False, ''),
        ],
        'action': '系统性危机，全面熔断'
    })

    triggered_count = sum(1 for l in lines if l['triggered'] and l['line'] != '防线7')

    result = {
        'asof': asof,
        'triggered_count': triggered_count,
        'systemic_confirmed': d7,
        'lines': lines
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS defense_v4 (
            asof_date TEXT PRIMARY KEY,
            triggered_count INTEGER, systemic_confirmed INTEGER, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO defense_v4
        (asof_date, triggered_count, systemic_confirmed, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, triggered_count, int(d7), json.dumps(lines)))
    conn.commit()
    conn.close()

    print(f"  已突破防线: {triggered_count}/7")
    print(f"  系统性危机: {'🚨 是' if d7 else '🟢 否'}\n")
    for l in lines:
        icon = '🚨' if l['triggered'] else '⏸️'
        print(f"  {icon} [{l['line']}] {l['name']}")
        for c in l['conditions']:
            mark = '✓' if c[1] else '✗'
            print(f"        [{mark}] {c[0]}: {c[2]}")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    evaluate_v4(asof)