"""engines_v3/fragility_engine.py - Fragility Engine (F0-F5)
[v5 - 宏观分位校准 + 相关性突变 + 飞书微观全量接入]
"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

def _load(conn, sid, limit=120):
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

def _get_pct(conn, sid):
    """从 series_percentile 获取 5 年历史分位"""
    try:
        df = pd.read_sql_query(
            "SELECT pct_5y FROM series_percentile WHERE series_id=? ORDER BY as_of_date DESC LIMIT 1",
            conn, params=(sid,)
        )
        if not df.empty and not pd.isna(df.iloc[0]['pct_5y']):
            return float(df.iloc[0]['pct_5y'])
    except Exception:
        pass
    return None

def _scale(value, lo, hi):
    """线性映射到 0-100，自动截断"""
    try:
        v = float(value)
        if pd.isna(v): return 50.0
        return float(np.clip((v - lo) / (hi - lo) * 100, 0, 100))
    except Exception:
        return 50.0

# ============ 10 个维度 ============

def calc_liquidity(conn):
    rrp = _load(conn, 'RRP_BALANCE', 30)
    res = _load(conn, 'RESERVE_BALANCE', 30)
    sofr = _load(conn, 'SOFR', 30)
    effr = _load(conn, 'EFFR', 30)
    score, comp = 0.0, {}
    if len(rrp) >= 1:
        pct = _get_pct(conn, 'RRP')
        if pct is not None:
            s = 100.0 - pct  # RRP越低压力越大
        else:
            s = _scale(2000 - float(rrp.iloc[-1]), 0, 2000)
        comp['RRP'] = round(s, 1)
        score += s * 0.4

    if len(res) >= 5:
        r_now, r_4w = float(res.iloc[-1]), float(res.iloc[-min(4, len(res))])
        chg = (r_now - r_4w) / r_4w if r_4w else 0
        s = _scale(-chg, -0.05, 0.05)
        comp['Reserves'] = round(s, 1)
        score += s * 0.3

    if len(sofr) >= 1 and len(effr) >= 1:
        spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
        s = _scale(spread, -2, 10)
        comp['SOFR-EFFR'] = round(s, 1)
        score += s * 0.3

    return min(score, 100), comp

def calc_leverage(conn):
    """杠杆维度 [v3: JPY 波动率加入周末过滤]"""
    vix = _load(conn, 'VIX', 60)
    jpy = _load(conn, 'USD_JPY', 60)
    score, comp = 0.0, {}

    # JPY 波动率：过滤周末（Yahoo JPY=X 会返回周六/日重复值）
    if len(jpy) >= 21:
        jpy_clean = jpy[jpy.index.dayofweek < 5]
        if len(jpy_clean) >= 21:
            vol = float(jpy_clean.pct_change().tail(20).std() * (252 ** 0.5))
            if not pd.isna(vol) and vol > 0:
                s = _scale(vol, 0.03, 0.15) # 下限调整，避免长期为 0
                comp['JPY_Vol'] = round(s, 1)
                score += s * 0.6
            else:
                comp['JPY_Vol'] = f'ZeroVol({vol:.6f})'
        else:
            comp['JPY_Vol'] = f'Skip({len(jpy_clean)}工作日)'
    else:
        comp['JPY_Vol'] = f'NoData({len(jpy)}条)'

    # VIX 波动率（VIX 本身是工作日数据，无需过滤）
    if len(vix) >= 20:
        vol = float(vix.pct_change().tail(20).std())
        if not pd.isna(vol):
            s = _scale(vol, 0.02, 0.08)
            comp['VIX_Vol'] = round(s, 1)
            score += s * 0.4

    return min(score, 100), comp

def calc_funding(conn):
    sofr = _load(conn, 'SOFR', 30)
    effr = _load(conn, 'EFFR', 30)
    res = _load(conn, 'RESERVE_BALANCE', 30)
    score, comp = 0.0, {}
    if len(sofr) >= 5 and len(effr) >= 5:
        spread = (float(sofr.ffill().iloc[-1]) - float(effr.ffill().iloc[-1])) * 100
        s = _scale(spread, -2, 10)
        comp['Spread'] = round(s, 1)
        score += s * 0.5
    if len(res) >= 5:
        s = _scale(3200000 - float(res.iloc[-1]), 0, 400000)
        comp['Reserves'] = round(s, 1)
        score += s * 0.5
    return min(score, 100), comp

def calc_crowding(conn):
    try:
        df = pd.read_sql_query(
            "SELECT stress_score FROM positioning_engine ORDER BY asof_date DESC LIMIT 1", conn
        )
        if not df.empty:
            v = float(df.iloc[0]['stress_score'])
            return min(v, 100), {'Positioning': round(v, 1)}
    except Exception:
        pass
    return 50.0, {'Positioning': 50.0}

def calc_mismatch(conn):
    y10 = _load(conn, 'YC10Y', 30)
    y30 = _load(conn, 'YC30Y', 30)
    tga = _load(conn, 'TGA_BALANCE', 30)
    score, comp = 0.0, {}
    if len(y30) >= 1 and len(y10) >= 1:
        curve = float(y30.iloc[-1]) - float(y10.iloc[-1])
        s = _scale(curve, 0, 1.0)
        comp['Curve_30_10'] = round(s, 1)
        score += s * 0.6
    if len(tga) >= 5:
        t_now, t_4w = float(tga.iloc[-1]), float(tga.iloc[-min(4, len(tga))])
        chg = abs((t_now - t_4w) / t_4w) if t_4w else 0
        s = _scale(chg, 0, 0.20)
        comp['TGA_Vol'] = round(s, 1)
        score += s * 0.4
    return min(score, 100), comp

def calc_valuation(conn):
    """估值/信用维度 [分位口径已校准]"""
    spx = _load(conn, 'SP500', 60)
    hyg = _load(conn, 'HY_SPREAD', 60)
    score, comp = 0.0, {}

    # 1. SPX 动量 (权重 50%)
    if len(spx) >= 20:
        chg = (float(spx.iloc[-1]) - float(spx.iloc[-min(20, len(spx))])) / float(spx.iloc[-min(20, len(spx))])
        s = _scale(chg, -0.05, 0.10)
        comp['SPX_Mom'] = round(s, 1)
        score += s * 0.5

    # 2. HY 信用利差 (权重 50%) —— 分位驱动
    pct_oas = _get_pct(conn, 'HY_SPREAD')
    pct_ccc = _get_pct(conn, 'HY_CCC_OAS')

    if pct_oas is not None and pct_ccc is not None:
        s = pct_oas * 0.4 + pct_ccc * 0.6
        comp['HY_Percentile'] = round(s, 1)
        score += s * 0.5
    elif len(hyg) >= 1:
        # 降级逻辑
        s = _scale(5.0 - float(hyg.iloc[-1]), -3, 3)
        comp['HY_Spread'] = round(s, 1)
        score += s * 0.5

    return min(score, 100), comp

def calc_correlation(conn):
    """跨资产相关性维度 [v2: 加入相关性突变信号]"""
    try:
        df = pd.read_sql_query(
            "SELECT avg_corr_20d, corr_break FROM contagion_engine "
            "ORDER BY asof_date DESC LIMIT 1", conn
        )
        if df.empty:
            return 50.0, {'Status': 'NoData'}

        corr = float(df.iloc[0]['avg_corr_20d'])
        brk = float(df.iloc[0]['corr_break']) if 'corr_break' in df.columns else 0.0

        if pd.isna(corr):
            return 50.0, {'Corr_20D': 50.0, 'Note': 'NaN'}

        base = _scale(corr, 0.0, 0.5)

        if not pd.isna(brk) and brk > 0:
            break_bonus = _scale(brk, 0.0, 0.3) * 0.4
        else:
            break_bonus = 0.0

        total = min(base + break_bonus, 100)

        return total, {
            'Corr_20D': round(corr, 3),
            'Corr_Break': round(brk, 3) if not pd.isna(brk) else 0.0,
            'Base': round(base, 1),
            'Break_Bonus': round(break_bonus, 1)
        }
    except Exception as e:
        return 50.0, {'Error': str(e)[:30]}

def calc_policy(conn):
    y2 = _load(conn, 'YC2Y', 30)
    score, comp = 0.0, {}

    # 1. 10Y 历史分位 (权重 60%)
    pct_10y = _get_pct(conn, 'US_10Y')
    if pct_10y is not None:
        comp['10Y_Pct'] = round(pct_10y, 1)
        score += pct_10y * 0.6

    # 2. 2Y 波动率 (权重 40%)
    if len(y2) >= 20:
        vol = float(y2.diff().tail(20).std())
        s = _scale(vol, 0.02, 0.15)
        comp['2Y_Vol'] = round(s, 1)
        score += s * 0.4

    return min(score, 100), comp

def calc_market_depth(conn):
    vix = _load(conn, 'VIX', 60)
    if len(vix) >= 20:
        vol = float(vix.pct_change().tail(20).std())
        s = _scale(vol, 0.02, 0.08)
        return s, {'VIX_Disp': round(s, 1)}
    return 50.0, {'VIX_Disp': 50.0}

def calc_crypto_micro(conn):
    """Crypto 微观结构脆弱性 [v4: 修复类型转换 + 接入飞书 HL 极度失衡]"""
    try:
        # 优先从 feishu_snapshot 读取（包含极端的 HL 深度和 FR）
        df_f = pd.read_sql_query(
            "SELECT coinbase_premium, bitget_btc_fr, hl_imbalance_btc "
            "FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1", conn
        )
        
        prem = fund = hl_imb = None
        if not df_f.empty:
            prem = df_f.iloc[0]['coinbase_premium']
            fund = df_f.iloc[0]['bitget_btc_fr']
            hl_imb = df_f.iloc[0]['hl_imbalance_btc']
        else:
            # 降级到原来的 crypto_micro 表
            df_c = pd.read_sql_query(
                "SELECT coinbase_premium, bitget_funding, long_short_ratio "
                "FROM crypto_micro ORDER BY asof_date DESC LIMIT 1", conn
            )
            if not df_c.empty:
                prem = df_c.iloc[0]['coinbase_premium']
                fund = df_c.iloc[0]['bitget_funding']

        score, comp = 0.0, {}
        total_weight = 0.0

        # 1. Coinbase 负溢价 (基础权重 25%)
        if prem is not None and not pd.isna(prem) and str(prem) != '':
            s = _scale(-float(prem), -0.2, 0.5)
            comp['CB_Premium'] = round(s, 1)
            score += s * 0.25
            total_weight += 0.25
            
        # 2. 极端资金费率 (绝对值为准，基础权重 25%)
        if fund is not None and not pd.isna(fund) and str(fund) != '':
            s = _scale(abs(float(fund)), 0, 30)
            comp['Extreme_FR'] = round(s, 1)
            score += s * 0.25
            total_weight += 0.25
            
        # 3. HL 订单簿极度失衡 (权重 50%！负值代表卖压重)
        if hl_imb is not None and not pd.isna(hl_imb) and str(hl_imb) != '':
            s = _scale(-float(hl_imb), -0.2, 0.8)
            comp['HL_Imbalance'] = round(s, 1)
            score += s * 0.50
            total_weight += 0.50

        if total_weight <= 0:
            return 50.0, {'Status': 'NoValidData'}

        final_score = score / total_weight
        return min(final_score, 100), comp

    except Exception as e:
        return 50.0, {'Error': str(e)[:30]}

# ============ 维度注册（权重总和 = 1.00）============
DIMENSIONS = [
    ('Liquidity',    calc_liquidity,    0.15),
    ('Leverage',     calc_leverage,     0.15),
    ('Funding',      calc_funding,      0.10),
    ('Crowding',     calc_crowding,     0.10),
    ('Mismatch',     calc_mismatch,     0.10),
    ('Valuation',    calc_valuation,    0.10),
    ('Correlation',  calc_correlation,  0.08),
    ('Policy',       calc_policy,       0.10),
    ('MarketDepth',  calc_market_depth, 0.07),
    ('Crypto_Micro', calc_crypto_micro, 0.10),
]

def calc_amplification(scores):
    high = sum(1 for v in scores.values() if v > 60)
    very_high = sum(1 for v in scores.values() if v > 75)
    amp = 1.0
    if high >= 2: amp += 0.15
    if high >= 4: amp += 0.15
    if high >= 6: amp += 0.15
    if very_high >= 2: amp += 0.15
    if very_high >= 4: amp += 0.15
    return round(min(amp, 2.0), 3)

def to_level(score):
    if score < 20: return 'F0_RESILIENT'
    elif score < 35: return 'F1_NORMAL'
    elif score < 50: return 'F2_VULNERABLE'
    elif score < 65: return 'F3_FRAGILE'
    elif score < 80: return 'F4_HIGHLY_FRAGILE'
    return 'F5_PRE_CRISIS'

def compute_fragility(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    scores, details = {}, {}
    try:
        for name, fn, w in DIMENSIONS:
            try:
                s, comp = fn(conn)
                s = float(np.clip(s, 0, 100))
                scores[name] = s
                details[name] = {'score': round(s, 1), 'components': comp, 'weight': w}
            except Exception as e:
                scores[name] = 50.0
                details[name] = {'score': 50.0, 'error': str(e)[:60], 'weight': w}
    finally:
        conn.close()

    base = sum(scores[n] * w for n, _, w in DIMENSIONS)
    amp = calc_amplification(scores)
    final = min(base * amp, 100)
    level = to_level(final)

    result = {
        'asof': asof,
        'fragility_score': round(final, 1),
        'base_fragility': round(base, 1),
        'amplification': amp,
        'level': level,
        'dimensions': details
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS fragility_engine (
        asof_date TEXT PRIMARY KEY, fragility_score REAL, base_fragility REAL,
        amplification REAL, level TEXT, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO fragility_engine
        (asof_date, fragility_score, base_fragility, amplification, level, detail)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (asof, final, base, amp, level, json.dumps(details)))
    conn.commit()
    conn.close()

    print(f"\n{'='*60}")
    print(f"  Fragility Engine - {asof}")
    print(f"{'='*60}")
    print(f"  Base Fragility:  {base:.1f}")
    print(f"  Amplification:   x{amp}")
    print(f"  Final Score:     {final:.1f}")
    print(f"  Level:           {level}\n")

    for n, _, w in DIMENSIONS:
        d = details[n]
        bar = '#' * int(d['score'] / 5)
        print(f"  {n:12s} [{w*100:4.0f}%] {d['score']:5.1f} {bar}")

        comps = d.get('components', {})
        if comps:
            items = list(comps.items())
            for i, (k, v) in enumerate(items):
                prefix = "    └─" if i == len(items) - 1 else "    ├─"
                if n == 'Liquidity':
                    if k == 'RRP': weight_str = "(40%)"
                    elif k == 'Reserves': weight_str = "(30%)"
                    elif k == 'SOFR-EFFR': weight_str = "(30%)"
                    else: weight_str = ""
                    print(f"{prefix} {k:12s} {weight_str:6s}: {v}")
                else:
                    print(f"{prefix} {k}: {v}")

    print(f"{'='*60}\n")
    return result

if __name__ == "__main__":
    compute_fragility(datetime.now().strftime('%Y-%m-%d'))