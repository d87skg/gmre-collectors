"""engines_v2/defense_matrix.py - 4道防线阶梯式执行矩阵"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def _load_latest_engine():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT engine_id, z_score FROM engine_latents
            WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)
        """, conn)
        return dict(zip(df['engine_id'], df['z_score']))
    finally:
        conn.close()


def _load_latest_regime():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT regime_probs FROM gms_regimes
            ORDER BY asof_date DESC LIMIT 1
        """, conn)
        return json.loads(df['regime_probs'].iloc[0]) if not df.empty else {}
    finally:
        conn.close()


def _load_usdjpy():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT timestamp, value FROM observations
            WHERE series_id='USD_JPY' ORDER BY timestamp DESC LIMIT 3
        """, conn)
        return float(df['value'].iloc[0]) if not df.empty else None
    finally:
        conn.close()


def evaluate_defenses(asof: str) -> dict:
    """评估4道防线状态"""
    z = _load_latest_engine()
    probs = _load_latest_regime()
    usdjpy = _load_usdjpy()

    inf = z.get('INF', 0.0)
    risk = z.get('RISK', 0.0)
    r4 = probs.get('R4', 0.0)
    r5 = probs.get('R5', 0.0)
    r4r5 = r4 + r5

    defenses = []

    # ============ 防线1：INF < -1.5（通缩确认）============
    d1_triggered = inf < -1.50
    d1_distance = inf - (-1.50)  # 正数=还差多少，负数=已突破
    defenses.append({
        'line': '防线1',
        'name': '通缩确认',
        'indicator': f'INF={inf:.3f}',
        'threshold': 'INF < -1.50',
        'triggered': d1_triggered,
        'distance': round(d1_distance, 3),
        'action': '增配黄金至30%，买入TLT现货（压注实际利率下行）',
        'target_state': '偏防守（黄金+长债）'
    })

    # ============ 防线2：RISK > +1.5（风险警报）============
    d2_triggered = risk > 1.50
    d2_distance = 1.50 - risk  # 正数=还差多少，负数=已突破
    defenses.append({
        'line': '防线2',
        'name': '风险警报',
        'indicator': f'RISK={risk:.3f}',
        'threshold': 'RISK > +1.50',
        'triggered': d2_triggered,
        'distance': round(d2_distance, 3),
        'action': '强制清仓高Beta权益与加密货币，高股息降至10%',
        'target_state': '强防守（现金+短债）'
    })

    # ============ 防线3：R4+R5 > 40%（体制切换）============
    d3_triggered = r4r5 > 0.40
    d3_distance = 0.40 - r4r5
    defenses.append({
        'line': '防线3',
        'name': '体制切换',
        'indicator': f'R4+R5={r4r5*100:.2f}%',
        'threshold': 'R4+R5 > 40%',
        'triggered': d3_triggered,
        'distance': round(d3_distance * 100, 2),  # 百分点
        'action': '启动极度防御：现金/BIL 40%，黄金30%，美债30%',
        'target_state': '绝对防御（完全Zero-Beta）'
    })

    # ============ 防线4：USD/JPY < 155（日元套利平仓）============
    d4_triggered = usdjpy is not None and usdjpy < 155.00
    d4_distance = (usdjpy - 155.00) if usdjpy else None
    defenses.append({
        'line': '防线4',
        'name': '日元套利平仓',
        'indicator': f'USD/JPY={usdjpy:.2f}' if usdjpy else 'N/A',
        'threshold': 'USD/JPY < 155.00',
        'triggered': d4_triggered,
        'distance': round(d4_distance, 2) if d4_distance is not None else None,
        'action': 'CARRY升级至STRESS：清仓所有杠杆头寸，行权USD/JPY Put',
        'target_state': '尾部平仓对冲模式'
    })

    # ============ 汇总 ============
    triggered_count = sum(1 for d in defenses if d['triggered'])

    if triggered_count == 0:
        overall = '⏸️ 全部防线未破，维持当前配置'
    elif triggered_count == 1:
        overall = '⚠️ 1道防线突破，启动对应动作'
    elif triggered_count == 2:
        overall = '🚨 2道防线突破，进入半防御模式'
    else:
        overall = '🚨🚨 多道防线突破，启动全面防御'

    result = {
        'asof': asof,
        'triggered_count': triggered_count,
        'overall': overall,
        'defenses': defenses
    }

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS defense_matrix (
            asof_date TEXT PRIMARY KEY,
            triggered_count INTEGER, overall TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO defense_matrix
        (asof_date, triggered_count, overall, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, triggered_count, overall, json.dumps(defenses)))
    conn.commit()
    conn.close()

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = evaluate_defenses(asof)
    print(f"\n{'='*60}")
    print(f"  4道防线执行矩阵 - {asof}")
    print(f"{'='*60}")
    print(f"  总体状态: {result['overall']}")
    print(f"  已突破防线数: {result['triggered_count']}/4\n")
    for d in result['defenses']:
        icon = '🚨' if d['triggered'] else '⏸️'
        print(f"  {icon} [{d['line']}] {d['name']}")
        print(f"      当前: {d['indicator']}  |  阈值: {d['threshold']}")
        if d['distance'] is not None:
            if d['triggered']:
                print(f"      ✅ 已突破（超出 {abs(d['distance'])}）")
            else:
                print(f"      距离触发: {d['distance']}")
        print(f"      动作: {d['action']}")
        print()
    print(f"{'='*60}\n")