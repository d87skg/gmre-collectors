import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# -*- coding: utf-8 -*-
"""engines_v3/lti_engine.py - LTI 清算透明度引擎（v3: 接入 data_proxy）"""
import sqlite3
import pandas as pd
from datetime import datetime
from core.data_proxy import load

DB_PATH = 'data/macro.db'

def _get_pct(conn, column_name, current_val, reverse=False):
    # 保留从 feishu_snapshot 读，但在没有数据时降级
    try:
        df = pd.read_sql_query(f"SELECT {column_name} FROM feishu_snapshot WHERE {column_name} IS NOT NULL AND {column_name} != ''", conn)
        if len(df) < 5: return None
        vals = df[column_name].astype(float)
        pct = (vals > current_val).mean() * 100 if reverse else (vals < current_val).mean() * 100
        return round(pct, 1)
    except Exception: return None

def compute_lti(asof=None):
    asof_str = asof or datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1", conn)
        
        # 🆕 走代理层获取官方数据
        try: fr_series = load(conn, 'BTC_FUNDING_RATE_1H', limit=1)
        except: fr_series = pd.Series(dtype=float)
        try: oi_series = load(conn, 'BTC_OI_VALUE_HIST', limit=289)
        except: oi_series = pd.Series(dtype=float)
    finally:
        conn.close()

    # 如果没有 feishu_snapshot 兜底，直接返回
    if df.empty and fr_series.empty:
        return {'status': 'NoData', 'lti_score': 0, 'level': 'UNKNOWN', 'details': {}}

    latest = df.iloc[0] if not df.empty else {}
    def to_f(v):
        try: return float(v) if pd.notna(v) and str(v) != '' else 0.0
        except: return 0.0

    fr_cross = to_f(latest.get('fr_cross_diff')) if not df.empty else 0.0
    bitget_fr = to_f(latest.get('bitget_btc_fr')) if not df.empty else (fr_series.iloc[-1] if not fr_series.empty else 0.0)
    hl_imb = to_f(latest.get('hl_imbalance_btc')) if not df.empty else 0.0

    scores, active_weights, details = {}, {}, {}

    if fr_cross != 0.0:
        scores['FR_Divergence'] = min(max(fr_cross * 5, 0), 100)
        active_weights['FR_Divergence'] = 0.25
        details['FR_Divergence'] = f"{scores['FR_Divergence']} (观测)"
    else:
        scores['FR_Divergence'], active_weights['FR_Divergence'], details['FR_Divergence'] = None, 0.0, "MISSING_DATA"

    if bitget_fr != 0.0:
        s2 = min(abs(bitget_fr), 100)
        scores['FR_Extreme'], active_weights['FR_Extreme'], details['FR_Extreme'] = s2, 0.25, f"{s2:.1f} (观测)"
    else:
        scores['FR_Extreme'], active_weights['FR_Extreme'], details['FR_Extreme'] = None, 0.0, "MISSING_DATA"

    if len(oi_series) >= 289:
        current_oi, prev_oi = oi_series.iloc[-1], oi_series.iloc[0]
        oi_change = (current_oi - prev_oi) / prev_oi * 100 if prev_oi else 0
        s3 = min(abs(oi_change) * 10, 100)
        scores['OI_Fragility'], active_weights['OI_Fragility'], details['OI_Fragility'] = s3, 0.25, f"{s3:.1f} (观测)"
    else:
        scores['OI_Fragility'], active_weights['OI_Fragility'], details['OI_Fragility'] = None, 0.0, "MISSING_DATA"

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
                s4 = min(abs(gold_5d) * 1000, 100); mode = 'LIQ_SELL'
            elif gold_5d > 0 and spx_5d < 0:
                s4 = 30.0; mode = 'RISK_OFF_SAFE'
            else:
                s4 = 20.0; mode = 'NORMAL'
            scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = s4, 0.25, f"{s4:.1f} ({mode})"
        else:
            scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = None, 0.0, "MISSING_DATA"
    except Exception:
        scores['Gold_Stock'], active_weights['Gold_Stock'], details['Gold_Stock'] = None, 0.0, "ERROR"

    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        return {'status': 'AllMissing', 'lti_score': 0, 'level': 'UNKNOWN', 'details': details, 'raw': {}}

    lti_score = sum(scores[k] * (w / total_weight) for k, w in active_weights.items() if w > 0)
    lti_score = min(max(lti_score, 0), 100)

    if lti_score >= 80: level = "EXTREME"
    elif lti_score >= 60: level = "HIGH"
    elif lti_score >= 40: level = "MEDIUM"
    else: level = "LOW"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS lti_engine (asof_date TEXT PRIMARY KEY, lti_score REAL, level TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO lti_engine (asof_date, lti_score, level) VALUES (?, ?, ?)""", (asof_str, lti_score, level))
    conn.commit()
    conn.close()

    return {
        'asof': asof_str, 'lti_score': round(lti_score, 1), 'level': level,
        'details': details, 'raw': {'bitget_fr': bitget_fr, 'hl_imbalance': hl_imb, 'fr_cross_diff': fr_cross}
    }

if __name__ == "__main__":
    res = compute_lti()
    print(f"  LTI 评分: {res['lti_score']}/100 ({res['level']})")