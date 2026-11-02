"""engines_v2/hedge_advisor.py - 尾部对冲规则引擎"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

# ============ 规则配置 ============
RULES = {
    'RRP_CRITICAL': {
        'condition': 'rrp_billion < 50',
        'hedge_action': 'BUY_USD_JPY_PUT_3M',
        'size_pct': 0.03,   # 3%仓位配置保护性期权
        'rationale': 'RRP耗尽，TGA补库将抽干准备金，日元套利平仓风险抬升'
    },
    'R4_HIGH_PROB': {
        'condition': 'r4_prob > 0.30',
        'hedge_action': 'BUY_SPX_PUT_6M',
        'size_pct': 0.04,
        'rationale': '深度衰退概率超30%，权益尾部风险对冲'
    },
    'PASSIVE_TIGHT': {
        'condition': 'inf_z < -1.0 and mon_z > 0.5',
        'hedge_action': 'BUY_30Y_TREASURY_CALL',
        'size_pct': 0.05,
        'rationale': '被动紧缩共振，长端利率下行对冲'
    },
    'NET_LIQ_DRAIN': {
        'condition': 'net_liq_20d_chg < -3000',
        'hedge_action': 'REDUCE_EQUITY_20PCT',
        'size_pct': 0.20,
        'rationale': '净流动性快速抽离，主动降风险'
    }
}


def _load_series(conn, sid, lookback=60):
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


def compute_hedge(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        # 流动性
        walcl = _load_series(conn, 'FED_WALCL', 60)
        tga   = _load_series(conn, 'TGA_BALANCE', 60)
        rrp   = _load_series(conn, 'RRP_BALANCE', 60)

        # 五引擎Z-score
        latests = pd.read_sql_query(
            "SELECT engine_id, z_score FROM engine_latents WHERE asof_date=?",
            conn, params=(asof,)
        )
        z = dict(zip(latests['engine_id'], latests['z_score']))

        # 体制概率
        regime = pd.read_sql_query(
            "SELECT regime_probs FROM gms_regimes WHERE asof_date=?",
            conn, params=(asof,)
        )
        probs = json.loads(regime['regime_probs'].iloc[0]) if not regime.empty else {}
    finally:
        conn.close()

    # 计算净流动性20日变化
    net_liq_20d_chg = 0.0
    rrp_now = 0.0
    if len(walcl) >= 5 and len(tga) >= 5 and len(rrp) >= 5:
        df = pd.concat([walcl, tga, rrp], axis=1).sort_index().ffill().bfill()
        df.columns = ['walcl', 'tga', 'rrp']
        df['walcl_b'] = df['walcl'] / 1000.0
        df['tga_b'] = df['tga'] / 1000.0
        df['rrp_b'] = df['rrp'] / 1000.0
        df['net_liq'] = df['walcl_b'] - df['tga_b'] - df['rrp_b']
        rrp_now = float(df['rrp_b'].iloc[-1])
        net_liq_20d_chg = float(df['net_liq'].iloc[-1] - df['net_liq'].iloc[-min(20, len(df))])

    # 规则评估
    actions = []
    inf_z = z.get('INF', 0.0)
    mon_z = z.get('MON', 0.0)
    r4 = probs.get('R4', 0)

    if rrp_now < 20:
        actions.append({
            'rule': 'RRP_CRITICAL',
            'action': 'BUY_USD_JPY_PUT_3M',
            'size_pct': 0.03,
            'rationale': RULES['RRP_CRITICAL']['rationale'],
            'trigger_value': f'RRP={rrp_now:.2f}十亿'
        })

    if r4 > 0.30:
        actions.append({
            'rule': 'R4_HIGH_PROB',
            'action': 'BUY_SPX_PUT_6M',
            'size_pct': 0.04,
            'rationale': RULES['R4_HIGH_PROB']['rationale'],
            'trigger_value': f'R4={r4*100:.1f}%'
        })

    if inf_z < -1.0 and mon_z > 0.5:
        actions.append({
            'rule': 'PASSIVE_TIGHT',
            'action': 'BUY_30Y_TREASURY_CALL',
            'size_pct': 0.05,
            'rationale': RULES['PASSIVE_TIGHT']['rationale'],
            'trigger_value': f'INF={inf_z:.2f},MON={mon_z:.2f}'
        })

    if net_liq_20d_chg < -1500:
        actions.append({
            'rule': 'NET_LIQ_DRAIN',
            'action': 'REDUCE_EQUITY_20PCT',
            'size_pct': 0.20,
            'rationale': RULES['NET_LIQ_DRAIN']['rationale'],
            'trigger_value': f'ΔNET_LIQ_20d={net_liq_20d_chg:.0f}十亿'
        })

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hedge_actions (
            asof_date TEXT, rule_name TEXT, action TEXT, size_pct REAL,
            rationale TEXT, trigger_value TEXT,
            PRIMARY KEY (asof_date, rule_name)
        )
    """)
    for a in actions:
        conn.execute("""
            INSERT OR REPLACE INTO hedge_actions
            (asof_date, rule_name, action, size_pct, rationale, trigger_value)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (asof, a['rule'], a['action'], a['size_pct'],
              a['rationale'], a['trigger_value']))
    conn.commit()
    conn.close()

    total_hedge = sum(a['size_pct'] for a in actions)
    return {'asof': asof, 'action_count': len(actions),
            'total_hedge_pct': total_hedge, 'actions': actions}


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    result = compute_hedge(asof)
    print(f"\n{'='*60}")
    print(f"  尾部对冲建议 - {asof}")
    print(f"{'='*60}")
    if result['action_count'] == 0:
        print("  ✅ 无对冲需求")
    else:
        print(f"  建议对冲仓位合计: {result['total_hedge_pct']*100:.1f}%\n")
        for a in result['actions']:
            print(f"  [{a['rule']}] {a['action']} ({a['size_pct']*100:.1f}%)")
            print(f"    → {a['rationale']}")
            print(f"    触发: {a['trigger_value']}\n")
    print(f"{'='*60}\n")