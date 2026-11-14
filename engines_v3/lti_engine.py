# -*- coding: utf-8 -*-
"""engines_v3/lti_engine.py - LTI 清算透明度引擎（v3.2: 带备用源追溯）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
from datetime import datetime
from core.data_proxy import load

DB_PATH = 'data/macro.db'

def compute_lti(asof=None):
    asof_str = asof or datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1", conn)
        try: fr_series = load(conn, 'BTC_FUNDING_RATE_1H', limit=1)
        except: fr_series = pd.Series(dtype=float)
        try: oi_series = load(conn, 'BTC_OI_VALUE_HIST', limit=289)
        except: oi_series = pd.Series(dtype=float)
    finally:
        conn.close()

    if df.empty and fr_series.empty:
        return {'status': 'NoData', 'lti_score': 0, 'level': 'UNKNOWN', 'details': {}}

    latest = df.iloc[0] if not df.empty else {}
    
    # 🆕 数据来源追溯：检查是否来自备用源
    if not df.empty:
        source_val = str(latest.get('source', ''))
        if 'fallback' in source_val or 'tencent' in source_val:
            print(f"  ⚠️ [数据追溯] 当前微观快照来自备用源 ({source_val})，决策置信度降级")

    def to_f(v):
        try: return float(v) if pd.notna(v) and str(v) != '' else 0.0
        except: return 0.0

    # 1. 提取飞书数据
    fr_cross = to_f(latest.get('fr_cross_diff')) if not df.empty else 0.0
    bitget_fr = to_f(latest.get('bitget_btc_fr')) if not df.empty else (fr_series.iloc[-1] if not fr_series.empty else 0.0)
    hl_imb = to_f(latest.get('hl_imbalance_btc')) if not df.empty else 0.0
    coinbase_prem = to_f(latest.get('coinbase_premium')) if not df.empty else 0.0
    stablecoin_chg = to_f(latest.get('stablecoin_30d_chg')) if not df.empty else 0.0

    scores, active_weights, details = {}, {}, {}

    # 维度 1：跨所资金费率差异 (15%)
    if fr_cross != 0.0:
        scores['FR_Divergence'] = min(max(fr_cross * 5, 0), 100)
        active_weights['FR_Divergence'] = 0.15
        details['FR_Divergence'] = f"{scores['FR_Divergence']:.1f} (观测)"
    else:
        scores['FR_Divergence'], active_weights['FR_Divergence'], details['FR_Divergence'] = None, 0.0, "MISSING_DATA"

    # 维度 2：极端费率 (15%)
    if bitget_fr != 0.0:
        s2 = min(abs(bitget_fr), 100)
        scores['FR_Extreme'], active_weights['FR_Extreme'], details['FR_Extreme'] = s2, 0.15, f"{s2:.1f} (观测)"
    else:
        scores['FR_Extreme'], active_weights['FR_Extreme'], details['FR_Extreme'] = None, 0.0, "MISSING_DATA"

    # 维度 3：持仓脆弱性 (15%)
    if len(oi_series) >= 20:
        current_oi, prev_oi = oi_series.iloc[-1], oi_series.iloc[-20]
        oi_change = (current_oi - prev_oi) / prev_oi * 100 if prev_oi else 0
        s3 = min(abs(oi_change) * 10, 100)
        scores['OI_Fragility'], active_weights['OI_Fragility'], details['OI_Fragility'] = s3, 0.15, f"{s3:.1f} (20期变幅 {oi_change:+.1f}%)"
    else:
        scores['OI_Fragility'], active_weights['OI_Fragility'], details['OI_Fragility'] = None, 0.0, f"MISSING_DATA (仅{len(oi_series)}行)"

    # 维度 4：美国机构现货溢价 (20%)
    if not df.empty and 'coinbase_premium' in latest:
        if coinbase_prem < 0:
            s4 = min(abs(coinbase_prem) / 0.2 * 100, 100)
            scores['US_Inst_Selling'], active_weights['US_Inst_Selling'], details['US_Inst_Selling'] = s4, 0.20, f"{s4:.1f} (抛压 {coinbase_prem:+.3f}%)"
        else:
            scores['US_Inst_Selling'], active_weights['US_Inst_Selling'], details['US_Inst_Selling'] = 0.0, 0.20, f"0.0 (溢价 {coinbase_prem:+.3f}%)"
    else:
        scores['US_Inst_Selling'], active_weights['US_Inst_Selling'], details['US_Inst_Selling'] = None, 0.0, "MISSING_DATA"

    # 维度 5：稳定币失血 (20%)
    sc_val = None
    for col in ['stablecoin_30d_chg', 'stablecoin_chg', 'stablecoin_mcap_30d']:
        if not df.empty and col in latest and pd.notna(latest[col]):
            sc_val = to_f(latest[col])
            break
            
    if sc_val is not None and sc_val != 0:
        if sc_val < 0:
            s5 = min(abs(sc_val) / 20.0 * 100, 100)
            scores['Stablecoin_Bleed'], active_weights['Stablecoin_Bleed'], details['Stablecoin_Bleed'] = s5, 0.20, f"{s5:.1f} (失血 {sc_val:+.1f}B)"
        else:
            scores['Stablecoin_Bleed'], active_weights['Stablecoin_Bleed'], details['Stablecoin_Bleed'] = 0.0, 0.20, f"0.0 (流入 {sc_val:+.1f}B)"
    else:
        scores['Stablecoin_Bleed'], active_weights['Stablecoin_Bleed'], details['Stablecoin_Bleed'] = None, 0.0, "MISSING_DATA"

    # 维度 6：金股联动 (15%)
    try:
        conn2 = sqlite3.connect(DB_PATH)
        try:
            gold = load(conn2, 'GOLD_PRICE', limit=30)
            spx = load(conn2, 'SP500', limit=30)
        finally: conn2.close()

        if len(gold) >= 5 and len(spx) >= 5:
            gold_5d = (float(gold.iloc[-1]) - float(gold.iloc[-5])) / float(gold.iloc[-5])
            spx_5d = (float(spx.iloc[-1]) - float(spx.iloc[-5])) / float(spx.iloc[-5])
            if gold_5d < 0 and abs(gold_5d) > abs(spx_5d) * 2:
                s6 = min(abs(gold_5d) * 1000, 100); mode = 'LIQ_SELL'
            elif gold_5d > 0 and spx_5d < 0:
                s6 = 30.0; mode = 'RISK_OFF_SAFE'
            else:
                s6 = 20.0; mode = 'NORMAL'
            scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = s6, 0.15, f"{s6:.1f} ({mode})"
        else:
            scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = None, 0.0, "MISSING_DATA"
    except Exception:
        scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = None, 0.0, "ERROR"

    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        return {'status': 'AllMissing', 'lti_score': 0, 'level': 'UNKNOWN', 'details': details, 'raw': {}}

    lti_score = sum(scores[k] * (w / total_weight) for k, w in active_weights.items() if w > 0 and scores[k] is not None)
    lti_score = min(max(lti_score, 0), 100)

    if lti_score >= 80: level = "EXTREME"
    elif lti_score >= 60: level = "HIGH"
    elif lti_score >= 40: level = "MEDIUM"
    else: level = "LOW"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS lti_engine (asof_date TEXT PRIMARY KEY, lti_score REAL, level TEXT)")
    conn.execute("INSERT OR REPLACE INTO lti_engine (asof_date, lti_score, level) VALUES (?, ?, ?)", (asof_str, lti_score, level))
    conn.commit(); conn.close()

    return {'asof': asof_str, 'lti_score': round(lti_score, 1), 'level': level, 'details': details, 'raw': {}}

if __name__ == "__main__":
    res = compute_lti()
    print(f"\n{'='*50}")
    print(f"  LTI 清算透明度引擎 - {res.get('asof', 'N/A')}")
    print(f"{'='*50}\n")
    print(f"  LTI 评分: {res['lti_score']}/100 ({res['level']})")
    for k, v in res['details'].items():
        print(f"    ├─ {k}: {v}")
    print(f"{'='*50}\n")