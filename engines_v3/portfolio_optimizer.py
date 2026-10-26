# engines_v3/portfolio_optimizer.py
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/macro.db'

def get_data_health():
    """检查核心数据源的新鲜度"""
    conn = sqlite3.connect(DB_PATH)
    critical_sids = ['YC10Y', 'VIX', 'GOLD_PRICE', 'USD_JPY', 'BTC_FUNDING_RATE_1H']
    health_report = []
    today = pd.Timestamp.now()
    
    for sid in critical_sids:
        row = conn.execute("SELECT timestamp FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
        if row:
            last_date = pd.Timestamp(row[0].split(' ')[0].split('T')[0])
            lag_days = (today - last_date).days
            if lag_days > 3:
                health_report.append(f"🔴 {sid} (滞后{lag_days}天)")
            elif lag_days > 1:
                health_report.append(f"🟡 {sid} (滞后{lag_days}天)")
        else:
            health_report.append(f"❌ {sid} (无数据)")
    conn.close()
    
    if not health_report:
        return "✅ 所有核心数据源最新"
    return "⚠️ 异常源: " + " | ".join(health_report)

def get_portfolio_advice(risk_gate, frag_score):
    """基于风险平价（目标波动率倒数加权）计算仓位，并加入拥挤度惩罚"""
    conn = sqlite3.connect(DB_PATH)
    
    # 1. 获取大类资产近 20 日序列计算波动率
    assets = {
        'BTC': 'BTC_SPOT_PRICE_1H',
        'GOLD': 'GOLD_PRICE',
        'US10Y': 'YC10Y'
    }
    vols = {}
    for name, sid in assets.items():
        df = pd.read_sql_query(f"SELECT value FROM observations WHERE series_id='{sid}' ORDER BY timestamp DESC LIMIT 20", conn)
        if len(df) > 5:
            returns = df['value'].pct_change().dropna()
            vols[name] = returns.std() if returns.std() > 0 else 0.02
        else:
            vols[name] = 0.02
            
    # 获取最新的 LTI 评分
    lti_row = conn.execute("SELECT lti_score FROM lti_engine ORDER BY asof_date DESC LIMIT 1").fetchone()
    current_lti = lti_row[0] if lti_row else 0
    conn.close()

    # 2. 根据 Risk Gate 设定总风险预算
    if risk_gate == 'RED':
        target_vol = 0.03
        base_cash = 0.60
    elif risk_gate == 'ORANGE':
        target_vol = 0.08
        base_cash = 0.30
    else:
        target_vol = 0.15
        base_cash = 0.10

    # 根据 Fragility 调整现金比例
    if frag_score > 60:
        base_cash += 0.10
        target_vol *= 0.8

    # 3. 风险平价分配 (1/波动率)
    inv_vols = {k: 1/v for k, v in vols.items()}
    total_inv_vol = sum(inv_vols.values())
    
    weights = {}
    total_risk_assets_weight = 1.0 - base_cash
    
    for k, inv_v in inv_vols.items():
        weight = (inv_v / total_inv_vol) * total_risk_assets_weight
        weight = weight * (target_vol / 0.10) 
        weights[k] = weight

    # ============ 核心修复：加入拥挤度惩罚 ============
    # 如果 LTI > 60 (多头极度拥挤)，强制削减 BTC 仓位 50%，并将仓位转入现金
    if current_lti > 60 and 'BTC' in weights:
        cut_weight = weights['BTC'] * 0.5
        weights['BTC'] -= cut_weight
        base_cash += cut_weight
        print(f"⚠️ [拥挤度惩罚] 当前 LTI={current_lti}，强制削减 BTC 仓位，增加现金。")
    # ==================================================

    # 归一化，转为百分比
    current_total = sum(weights.values())
    if current_total > 0:
        scale = (total_risk_assets_weight * 100) / current_total
        weights = {k: round(v * scale, 1) for k, v in weights.items()}

    return weights, round(base_cash * 100, 1)