"""engines_v3/transmission_graph.py - Transmission Graph (VS3)
追踪 3 条主链的状态：
  Chain A: Oil → Inflation → Fed → Rates → FCI → Risk Assets
  Chain B: BOJ → JPY → Carry → Leverage → Forced Selling
  Chain C: RRP → Buffer → Reserves → Funding → Liquidity

核心升级：
  1. 引入四态判定：INACTIVE / WATCH / ACTIVE / UNKNOWN。
  2. 分离“数据缺失”与“未触发”，强制输出数据质量。
  3. 链级激活度采用“有效边加权平均 × 传导完备度”，避免数据缺失导致假阴性。
"""
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


def _chg(series, window=5):
    """计算变化率，如果数据不足返回 None 触发 UNKNOWN"""
    if len(series) < window + 1:
        return None
    s = series.dropna()
    prev = float(s.iloc[-window - 1])
    if prev == 0:
        return 0.0
    return (float(s.iloc[-1]) - prev) / abs(prev)


def _normalize(val, lo, hi):
    return float(np.clip((val - lo) / (hi - lo), 0, 1))


def edge_status(activation, is_unknown=False):
    """边的四态：UNKNOWN / INACTIVE / WATCH / ACTIVE"""
    if is_unknown:
        return 'UNKNOWN'
    if activation < 0.15:
        return 'INACTIVE'
    elif activation < 0.35:
        return 'WATCH'
    else:
        return 'ACTIVE'


def chain_status(activation, unknown_edges, total_edges):
    """链的四态判定"""
    if unknown_edges == total_edges:
        return 'UNKNOWN'  # 全盲，无法判定
    if unknown_edges > 0 and activation < 0.15:
        return 'WATCH'    # 数据不全，但当前没爆发，列为观察
    if activation < 0.15:
        return 'INACTIVE'
    elif activation < 0.40:
        return 'WATCH'
    else:
        return 'ACTIVE'


# ============ Chain A: Oil → Inflation → Fed → Rates → FCI → Risk ============

def chain_a(conn):
    wti = _load(conn, 'WTI_OIL', 60)
    cpi = _load(conn, 'CPIAUCSL', 60)
    y2 = _load(conn, 'YC2Y', 60)
    y10 = _load(conn, 'YC10Y', 60)
    vix = _load(conn, 'VIX', 60)
    hyg = _load(conn, 'HY_SPREAD', 60)

    edges = []

    # Edge 1: Oil → Inflation
    oil_chg = _chg(wti, 5)
    if oil_chg is None:
        edges.append({'edge': 'Oil → Inflation', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        oil_activation = _normalize(oil_chg, 0.0, 0.10) if oil_chg > 0 else 0.0
        edges.append({'edge': 'Oil → Inflation', 'activation': round(oil_activation, 3),
                      'status': edge_status(oil_activation), 'value': f'Oil 5D={oil_chg*100:+.2f}%'})

    # Edge 2: Inflation → Fed
    y2_chg_bp = _chg(y2, 5) * 100 if _chg(y2, 5) is not None else None
    if y2_chg_bp is None:
        edges.append({'edge': 'Inflation → Fed', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        fed_activation = _normalize(abs(y2_chg_bp), 5, 40) if oil_activation > 0.2 else 0.0
        edges.append({'edge': 'Inflation → Fed', 'activation': round(fed_activation, 3),
                      'status': edge_status(fed_activation), 'value': f'2Y 5D={y2_chg_bp:+.1f}bp'})

    # Edge 3: Fed → 10Y
    y10_chg_bp = _chg(y10, 5) * 100 if _chg(y10, 5) is not None else None
    if y10_chg_bp is None:
        edges.append({'edge': 'Fed → 10Y', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        y10_activation = _normalize(abs(y10_chg_bp), 5, 30) if fed_activation > 0.2 else 0.0
        edges.append({'edge': 'Fed → 10Y', 'activation': round(y10_activation, 3),
                      'status': edge_status(y10_activation), 'value': f'10Y 5D={y10_chg_bp:+.1f}bp'})

    # Edge 4: 10Y → FCI
    vix_chg = _chg(vix, 5)
    if vix_chg is None:
        edges.append({'edge': 'Rates → FCI', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        fci_activation = _normalize(vix_chg, 0.0, 0.15) if y10_activation > 0.2 else 0.0
        edges.append({'edge': 'Rates → FCI', 'activation': round(fci_activation, 3),
                      'status': edge_status(fci_activation), 'value': f'VIX 5D={vix_chg*100:+.2f}%'})

    # Edge 5: FCI → Credit
    hyg_chg = _chg(hyg, 5)
    if hyg_chg is None:
        edges.append({'edge': 'FCI → Credit', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        credit_activation = _normalize(hyg_chg, 0.0, 0.10) if fci_activation > 0.2 else 0.0
        edges.append({'edge': 'FCI → Credit', 'activation': round(credit_activation, 3),
                      'status': edge_status(credit_activation), 'value': f'HY 5D={hyg_chg*100:+.2f}%'})

    return edges


# ============ Chain B: BOJ → JPY → Carry → Leverage → Forced Selling ============

def chain_b(conn):
    jp10y = _load(conn, 'JP_10Y_YIELD', 60)
    usdjpy = _load(conn, 'USD_JPY', 60)
    vix = _load(conn, 'VIX', 60)
    nasdaq = _load(conn, 'SP500', 60)

    edges = []

    # Edge 1: BOJ → JPY
    jp10y_chg = _chg(jp10y, 20)
    if jp10y_chg is None:
        edges.append({'edge': 'BOJ → JPY', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        jpy_activation = _normalize(jp10y_chg, 0.0, 0.15) if jp10y_chg > 0 else 0.0
        edges.append({'edge': 'BOJ → JPY', 'activation': round(jpy_activation, 3),
                      'status': edge_status(jpy_activation), 'value': f'JP10Y 20D={jp10y_chg*100:+.2f}%'})

    # Edge 2: JPY → Carry
    usdjpy_chg = _chg(usdjpy, 5)
    if usdjpy_chg is None:
        edges.append({'edge': 'JPY → Carry', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        carry_activation = _normalize(-usdjpy_chg, 0.0, 0.05) if usdjpy_chg < 0 else 0.0
        edges.append({'edge': 'JPY → Carry', 'activation': round(carry_activation, 3),
                      'status': edge_status(carry_activation), 'value': f'USDJPY 5D={usdjpy_chg*100:+.2f}%'})

    # Edge 3: Carry → Leverage
    vix_chg = _chg(vix, 5)
    if vix_chg is None:
        edges.append({'edge': 'Carry → Leverage', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        leverage_activation = _normalize(vix_chg, 0.0, 0.20) if carry_activation > 0.2 else 0.0
        edges.append({'edge': 'Carry → Leverage', 'activation': round(leverage_activation, 3),
                      'status': edge_status(leverage_activation), 'value': f'VIX 5D={vix_chg*100:+.2f}%'})

    # Edge 4: Leverage → Forced Selling
    try:
        df = pd.read_sql_query(
            "SELECT avg_corr_20d FROM contagion_engine ORDER BY asof_date DESC LIMIT 1",
            conn
        )
        if not df.empty:
            corr = float(df.iloc[0]['avg_corr_20d'])
            selling_activation = _normalize(corr, 0.0, 0.5) if leverage_activation > 0.2 else 0.0
            edges.append({'edge': 'Leverage → Forced Selling', 'activation': round(selling_activation, 3),
                          'status': edge_status(selling_activation), 'value': f'Corr_20d={corr:+.3f}'})
        else:
            edges.append({'edge': 'Leverage → Forced Selling', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    except Exception:
        edges.append({'edge': 'Leverage → Forced Selling', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})

    return edges


# ============ Chain C: RRP → Buffer → Reserves → Funding → Liquidity ============

def chain_c(conn):
    rrp = _load(conn, 'RRP_BALANCE', 60)
    res = _load(conn, 'RESERVE_BALANCE', 60)
    sofr = _load(conn, 'SOFR', 60)
    effr = _load(conn, 'EFFR', 60)
    vix = _load(conn, 'VIX', 60)

    edges = []

    # Edge 1: RRP → Buffer
    if len(rrp) >= 1:
        rrp_now = float(rrp.iloc[-1])
        buffer_activation = _normalize(500 - rrp_now, 0, 500) if rrp_now < 500 else 0.0
        edges.append({'edge': 'RRP → Buffer', 'activation': round(buffer_activation, 3),
                      'status': edge_status(buffer_activation), 'value': f'RRP={rrp_now:.1f}B'})
    else:
        edges.append({'edge': 'RRP → Buffer', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})

    # Edge 2: Buffer → Reserves
    if len(res) >= 5:
        r_chg = _chg(res, 4)
        if r_chg is None:
            edges.append({'edge': 'Buffer → Reserves', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
        else:
            res_activation = _normalize(-r_chg, 0.0, 0.02) if r_chg < 0 else 0.0
            edges.append({'edge': 'Buffer → Reserves', 'activation': round(res_activation, 3),
                          'status': edge_status(res_activation), 'value': f'Reserves 4W={r_chg*100:+.2f}%'})
    else:
        edges.append({'edge': 'Buffer → Reserves', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})

    # Edge 3: Reserves → Funding
    if len(sofr) >= 1 and len(effr) >= 1:
        spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
        funding_activation = _normalize(spread, 0, 10) if spread > 0 else 0.0
        edges.append({'edge': 'Reserves → Funding', 'activation': round(funding_activation, 3),
                      'status': edge_status(funding_activation), 'value': f'SOFR-EFFR={spread:+.2f}bp'})
    else:
        edges.append({'edge': 'Reserves → Funding', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})

    # Edge 4: Funding → Market Liquidity
    vix_chg = _chg(vix, 5)
    if vix_chg is None:
        edges.append({'edge': 'Funding → Market Liquidity', 'activation': 0.0, 'status': 'UNKNOWN', 'value': 'N/A'})
    else:
        mkt_liq_activation = _normalize(vix_chg, 0.0, 0.15) if funding_activation > 0.2 else 0.0
        edges.append({'edge': 'Funding → Market Liquidity', 'activation': round(mkt_liq_activation, 3),
                      'status': edge_status(mkt_liq_activation), 'value': f'VIX 5D={vix_chg*100:+.2f}%'})

    return edges


# ============ 主入口 ============

CHAINS = [
    ('Chain A: Oil → Inflation → Fed → Rates → Risk', chain_a),
    ('Chain B: BOJ → JPY → Carry → Leverage → Selling', chain_b),
    ('Chain C: RRP → Buffer → Reserves → Funding → Liquidity', chain_c),
]


def compute_transmission(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    result = {'asof': asof, 'chains': []}

    try:
        for chain_name, fn in CHAINS:
            try:
                edges = fn(conn)

                # 统计各状态数量
                unknown_edges = sum(1 for e in edges if e['status'] == 'UNKNOWN')
                valid_edges = [e for e in edges if e['status'] != 'UNKNOWN']
                n_valid = len(valid_edges)
                n_total = len(edges)

                # 计算有效边加权平均（剔除 UNKNOWN 避免假阴性）
                if n_valid > 0:
                    weighted_avg = sum(e['activation'] for e in valid_edges) / n_valid
                    active_count = sum(1 for e in valid_edges if e['activation'] > 0.15)
                    completeness = active_count / n_valid
                else:
                    weighted_avg = 0.0
                    completeness = 0.0

                # 链级激活度
                chain_activation = weighted_avg * completeness
                c_status = chain_status(chain_activation, unknown_edges, n_total)

                result['chains'].append({
                    'name': chain_name,
                    'activation': round(chain_activation, 3),
                    'weighted_avg': round(weighted_avg, 3),
                    'completeness': round(completeness, 3),
                    'active_edges': f'{active_count}/{n_valid}',
                    'unknown_edges': unknown_edges,
                    'status': c_status,
                    'edges': edges
                })
            except Exception as e:
                result['chains'].append({
                    'name': chain_name, 'activation': 0.0, 'status': 'UNKNOWN',
                    'unknown_edges': len(CHAINS), 'edges': [], 'error': str(e)[:80]
                })
    finally:
        conn.close()

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS transmission_graph (
        asof_date TEXT PRIMARY KEY, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO transmission_graph
        (asof_date, detail) VALUES (?, ?)""",
        (asof, json.dumps(result['chains'])))
    conn.commit()
    conn.close()

    # 打印详情
    print(f"\n{'='*72}")
    print(f"  Transmission Graph - {asof}")
    print(f"{'='*72}\n")

    for chain in result['chains']:
        icon = {
            'INACTIVE': '⚪', 'WATCH': '🟡', 'ACTIVE': '🚨', 'UNKNOWN': '❓'
        }.get(chain['status'], '?')
        
        print(f"  {icon} {chain['name']}")
        print(f"      状态: {chain['status']} | 激活度: {chain['activation']:.3f} | "
              f"完备度: {chain.get('active_edges', '0/0')} | 盲区边数: {chain.get('unknown_edges', 0)}")
        
        if 'weighted_avg' in chain:
            print(f"      有效边加权均值: {chain['weighted_avg']:.3f}")
            
        for e in chain['edges']:
            sub_icon = {
                'INACTIVE': '  ·', 'WATCH': '  🟡', 'ACTIVE': '  🚨', 'UNKNOWN': '  ❓'
            }.get(e['status'], '  ?')
            print(f"{sub_icon} {e['edge']:35s} A={e['activation']:.2f} | {e['value']}")
        print()

    print(f"{'='*72}\n")
    return result


if __name__ == "__main__":
    compute_transmission(datetime.now().strftime('%Y-%m-%d'))