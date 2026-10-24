"""engines_v3/scenario_tree.py - VS6: 情景树分析"""
import sqlite3
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _read_state(conn, asof):
    """读取当前所有状态"""
    state = {'asof': asof}

    # Fragility
    try:
        r = conn.execute("SELECT fragility_score, level FROM fragility_engine WHERE asof_date=?", (asof,)).fetchone()
        if r:
            state['frag_score'] = r[0]
            state['frag_level'] = r[1]
        else:
            state['frag_score'] = 50
            state['frag_level'] = 'F2_VULNERABLE'
    except Exception:
        state['frag_score'] = 50
        state['frag_level'] = 'F2_VULNERABLE'

    # Stress
    try:
        r = conn.execute("SELECT overall FROM stress_overlay_v2 WHERE asof_date=?", (asof,)).fetchone()
        state['stress'] = r[0] if r else 'S0_NORMAL'
    except Exception:
        state['stress'] = 'S0_NORMAL'

    # Shock
    try:
        r = conn.execute("SELECT primary_shock FROM shock_engine WHERE asof_date=?", (asof,)).fetchone()
        state['shock'] = r[0] if r else 'NONE'
    except Exception:
        state['shock'] = 'NONE'

    # Regime
    try:
        r = conn.execute("SELECT regime_label FROM gms_regimes WHERE asof_date=?", (asof,)).fetchone()
        state['regime'] = r[0] if r else 'R0'
    except Exception:
        state['regime'] = 'R0'

    return state


def _calc_probabilities(state):
    """基于状态计算4个情景概率"""
    frag = state['frag_score']
    stress = state['stress']
    shock = state['shock']

    # Base（基准）
    base = 0.55
    if frag > 65:
        base -= 0.15
    if 'FUNDING' in stress or 'CREDIT' in stress:
        base -= 0.10

    # Upside（乐观）
    upside = 0.20
    if frag > 65:
        upside -= 0.05
    if shock == 'NONE':
        upside += 0.05

    # Downside（悲观）
    downside = 0.18
    if frag > 65:
        downside += 0.10
    if 'FUNDING' in stress or 'CREDIT' in stress:
        downside += 0.08

    # Tail（尾部）
    tail = 0.07
    if frag > 80:
        tail += 0.10
    if 'SYSTEMIC' in stress:
        tail += 0.20

    # 归一化
    total = base + upside + downside + tail
    return {
        'BASE': round(base / total, 3),
        'UPSIDE': round(upside / total, 3),
        'DOWNSIDE': round(downside / total, 3),
        'TAIL': round(tail / total, 3)
    }


def compute_scenarios(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        state = _read_state(conn, asof)
    finally:
        conn.close()

    probs = _calc_probabilities(state)

    scenarios = {
        'BASE': {
            'name': '基准情景',
            'probability': probs['BASE'],
            'trigger': '利率震荡 + 风险偏好温和 + 无新冲击',
            'transmission': 'Rates 稳定 → FCI 稳定 → 风险资产震荡',
            'expected_regime': 'R0/R1 维持',
            'asset_impact': {
                'BTC': '震荡', 'GOLD': '偏强', 'SPX': '震荡',
                'UST10Y': '4.7-5.0%', 'USD': '中性'
            },
            'invalidation': 'Oil > $110 或 10Y > 5.2%',
            'duration': '2-6周'
        },
        'UPSIDE': {
            'name': '乐观情景',
            'probability': probs['UPSIDE'],
            'trigger': 'Oil回落 + 通胀持续下行 + Fed 释放鸽派',
            'transmission': 'Oil↓ → Inflation↓ → Fed Repricing↓ → Rates↓ → 风险资产↑',
            'expected_regime': 'R0 → R1',
            'asset_impact': {
                'BTC': '上涨', 'GOLD': '震荡', 'SPX': '上涨',
                'UST10Y': '< 4.7%', 'USD': '偏弱'
            },
            'invalidation': 'Oil 反弹 + CPI 超预期',
            'duration': '2-4周'
        },
        'DOWNSIDE': {
            'name': '悲观情景',
            'probability': probs['DOWNSIDE'],
            'trigger': 'Fed 加息 + 通胀预期抬升 + 长端利率破5%',
            'transmission': 'Fed↑ → 2Y↑ → 10Y↑ → FCI 收紧 → 权益估值压缩',
            'expected_regime': 'R3 衰退预警',
            'asset_impact': {
                'BTC': '下跌', 'GOLD': '震荡或下跌',
                'SPX': '下跌', 'UST10Y': '> 5%', 'USD': '偏强'
            },
            'invalidation': 'Fed 转鸽 + 通胀快速下行',
            'duration': '4-8周'
        },
        'TAIL': {
            'name': '尾部情景',
            'probability': probs['TAIL'],
            'trigger': '日元套利平仓加速 + RRP耗尽后准备金压力 + 信用利差走阔',
            'transmission': 'BOJ → JPY → Carry Unwind → Leverage ↓ → Forced Selling → Contagion',
            'expected_regime': 'R4/R5/R6',
            'asset_impact': {
                'BTC': '大跌', 'GOLD': '短期下跌然后反弹',
                'SPX': '大跌', 'UST10Y': '收益率快速下行',
                'USD': '短期飙升后回落'
            },
            'invalidation': 'USDJPY 稳定 > 155 + VIX < 20',
            'duration': '1-4周'
        }
    }

    output = {
        'asof': asof,
        'state': state,
        'scenarios': scenarios
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS scenario_tree (
        asof_date TEXT PRIMARY KEY, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO scenario_tree
        (asof_date, detail) VALUES (?, ?)""",
        (asof, json.dumps(scenarios)))
    conn.commit()
    conn.close()

    # 打印
    print(f"\n{'='*70}")
    print(f"  Scenario Tree - {asof}")
    print(f"{'='*70}\n")
    print(f"  当前状态: Fragility={state['frag_level']} | Stress={state['stress']} | Shock={state['shock']}\n")

    for key in ['BASE', 'UPSIDE', 'DOWNSIDE', 'TAIL']:
        s = scenarios[key]
        bar = '#' * int(s['probability'] * 50)
        print(f"  【{s['name']}】 P={s['probability']*100:.1f}% {bar}")
        print(f"      触发: {s['trigger']}")
        print(f"      传导: {s['transmission']}")
        print(f"      目标Regime: {s['expected_regime']}")
        print(f"      失效条件: {s['invalidation']}")
        print(f"      时长: {s['duration']}")
        print()

    print(f"{'='*70}\n")
    return output


if __name__ == "__main__":
    compute_scenarios(datetime.now().strftime('%Y-%m-%d'))