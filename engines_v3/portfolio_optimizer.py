# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import numpy as np
import yaml
import os

DB_PATH = 'data/macro.db'

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'risk_limits.yaml')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️ 无法读取 risk_limits.yaml，使用默认值: {e}")
        return None

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
    cfg = load_config()
    if cfg:
        cfg_opt = cfg.get('portfolio_optimizer', {})
        base_cash_red = cfg_opt.get('base_cash', {}).get('red', 0.60)
        target_vol_red = cfg_opt.get('target_vol', {}).get('red', 0.03)
        # ... 你可以自行扩展其他状态
        caps_floor = cfg_opt.get('caps_copper_cash_floor', 0.50)
        frag_add = cfg_opt.get('frag_score_cash_add', 0.10)
        max_w = cfg_opt.get('max_single_asset_weight', 15.0)
        duration = cfg_opt.get('us10y_duration', 7.5)
    else:
        # 兜底默认值
        base_cash_red, target_vol_red = 0.60, 0.03
        caps_floor, frag_add, max_w, duration = 0.50, 0.10, 15.0, 7.5

    conn = sqlite3.connect(DB_PATH)
    assets = {'BTC': 'BTC_SPOT_PRICE_1H', 'GOLD': 'GOLD_PRICE', 'US10Y': 'YC10Y'}
    vols = {}
    
    for name, sid in assets.items():
        df = pd.read_sql_query(f"SELECT timestamp, value FROM observations WHERE series_id='{sid}' ORDER BY timestamp ASC LIMIT 30", conn)
        if len(df) > 5:
            s = df['value'].ffill()
            if name == 'US10Y':
                yield_diff = s.diff() / 100.0 
                bond_returns = -duration * yield_diff
                vol = bond_returns.dropna().std()
            else:
                vol = s.pct_change().dropna().std()
            vols[name] = vol if pd.notna(vol) and np.isfinite(vol) else 0.02
        else:
            vols[name] = 0.02
    conn.close()

    if risk_gate == 'RED':
        target_vol, base_cash = target_vol_red, base_cash_red
    elif risk_gate == 'ORANGE':
        target_vol, base_cash = 0.08, 0.30
    else:
        target_vol, base_cash = 0.15, 0.10

    if caps_cu >= 80:
        base_cash = max(base_cash, caps_floor)
        target_vol *= 0.5

    if frag_score > 60:
        base_cash += frag_add
        target_vol *= 0.8

    inv_vols = {k: 1/v if v > 1e-6 else 50 for k, v in vols.items()}
    total_inv_vol = sum(inv_vols.values())
    total_risk_assets_weight = 1.0 - base_cash
    
    weights = {k: (inv_v / total_inv_vol) * total_risk_assets_weight * (target_vol / 0.10) for k, inv_v in inv_vols.items()}

    current_total = sum(weights.values())
    if current_total > 0:
        scale = (total_risk_assets_weight * 100) / current_total
        weights = {k: round(v * scale, 1) for k, v in weights.items()}

    if risk_gate == 'RED' or caps_cu >= 80:
        excess_sum = 0.0
        for asset, w in weights.items():
            if w > max_w:
                excess_sum += (w - max_w)
                weights[asset] = max_w
        if excess_sum > 0:
            base_cash += (excess_sum / 100.0)
            print(f"⚠️ [风控硬截断] 单一资产超过 {max_w}% 红线，已强制剥离 {excess_sum:.1f}% 至现金。")

    return weights, round(base_cash * 100, 1)