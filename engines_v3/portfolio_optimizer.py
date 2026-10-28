# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = 'data/macro.db'

def get_data_health():
    try:
        conn = sqlite3.connect(DB_PATH)
        critical_sids = ['YC10Y', 'VIX', 'GOLD_PRICE', 'USD_JPY', 'BTC_FUNDING_RATE_1H']
        health_report = []
        today = pd.Timestamp.now()
        for sid in critical_sids:
            row = conn.execute("SELECT timestamp FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 1", (sid,)).fetchone()
            if row:
                last_date = pd.Timestamp(row[0].split(' ')[0].split('T')[0])
                lag_days = (today - last_date).days
                if lag_days > 3: health_report.append(f"🔴 {sid} (滞后{lag_days}天)")
                elif lag_days > 1: health_report.append(f"🟡 {sid} (滞后{lag_days}天)")
        conn.close()
        return "✅ 所有核心数据源最新" if not health_report else "⚠️ 异常源: " + " | ".join(health_report)
    except Exception:
        return "❌ 健康度读取失败"

def get_portfolio_advice(risk_gate, frag_score, caps_cu=0):
    conn = sqlite3.connect(DB_PATH)
    assets = {'BTC': 'BTC_SPOT_PRICE_1H', 'GOLD': 'GOLD_PRICE', 'US10Y': 'YC10Y'}
    vols = {}
    for name, sid in assets.items():
        df = pd.read_sql_query(f"SELECT value FROM observations WHERE series_id='{sid}' ORDER BY timestamp DESC LIMIT 20", conn)
        vols[name] = df['value'].pct_change().dropna().std() if len(df) > 5 else 0.02
    conn.close()

    if risk_gate == 'RED':
        target_vol, base_cash = 0.03, 0.60
    elif risk_gate == 'ORANGE':
        target_vol, base_cash = 0.08, 0.30
    else:
        target_vol, base_cash = 0.15, 0.10

    # 如果沪铜极值逼仓，强行将现金比例拉高到 50% 以上
    if caps_cu >= 80:
        base_cash = max(base_cash, 0.50)
        target_vol *= 0.5

    if frag_score > 60:
        base_cash += 0.10
        target_vol *= 0.8

    inv_vols = {k: 1/v for k, v in vols.items()}
    total_inv_vol = sum(inv_vols.values())
    total_risk_assets_weight = 1.0 - base_cash
    weights = {k: (inv_v / total_inv_vol) * total_risk_assets_weight * (target_vol / 0.10) for k, inv_v in inv_vols.items()}

    current_total = sum(weights.values())
    if current_total > 0:
        scale = (total_risk_assets_weight * 100) / current_total
        weights = {k: round(v * scale, 1) for k, v in weights.items()}

    # 核心硬性风控：Gate 为 RED 或 沪铜逼仓时，单一资产不超过 15%
    if risk_gate == 'RED' or caps_cu >= 80:
        excess_sum = 0.0
        for asset, w in weights.items():
            if w > 15.0:
                excess_sum += (w - 15.0)
                weights[asset] = 15.0
        if excess_sum > 0:
            base_cash += (excess_sum / 100.0)
            print(f"⚠️ [风控硬截断] 单一资产超过 15% 红线，已强制剥离 {excess_sum:.1f}% 至现金。")

    return weights, round(base_cash * 100, 1)