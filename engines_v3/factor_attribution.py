# -*- coding: utf-8 -*-
"""engines_v3/factor_attribution.py - 极简因子归因（长周期回溯版）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

DB_PATH = 'data/macro.db'

def _load_daily_series(conn, sid, limit=250):
    """拉取最多250天日频历史，兼容小时线降采样"""
    try:
        df = pd.read_sql_query(
            f"SELECT timestamp AS dt, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT 5000",
            conn, params=(sid,)
        )
        if not df.empty:
            df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
            df = df.dropna(subset=['dt'])
            df['date_only'] = df['dt'].dt.date
            # 按天聚合，取最后一条
            df = df.groupby('date_only').last().reset_index()
            df['dt'] = pd.to_datetime(df['date_only'])
            df = df.sort_values('dt').set_index('dt')['value'].astype(float)
            return df.tail(limit)
    except Exception:
        pass
    return pd.Series(dtype=float)

def compute_factor_attribution(asof: str, port_weights: dict) -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        assets = {
            'DXY': _load_daily_series(conn, 'DXY_PROXY', 250),
            'US10Y': _load_daily_series(conn, 'YC10Y', 250),
            'SP500': _load_daily_series(conn, 'SP500', 250),
            'GOLD': _load_daily_series(conn, 'GOLD_PRICE', 250),
            'BTC': _load_daily_series(conn, 'BTC_SPOT_PRICE_1H', 250),
        }
    finally:
        conn.close()

    # 合并收益率矩阵
    rets_df = pd.DataFrame()
    for k, v in assets.items():
        if len(v) > 0:
            rets_df[k] = v.pct_change()
    
    rets_df = rets_df.dropna()
    if len(rets_df) < 20:
        return {'status': 'INSUFFICIENT_DATA', 'msg': f'有效交集仅 {len(rets_df)} 天'}

    # PCA
    scaler = StandardScaler()
    scaled_rets = scaler.fit_transform(rets_df)
    pca = PCA(n_components=3)
    pca.fit(scaled_rets)
    
    # 计算组合收益率
    port_rets = np.zeros(len(rets_df))
    has_weight = False
    for asset, weight in port_weights.items():
        if asset in rets_df.columns and weight > 0:
            port_rets += rets_df[asset].values * weight
            has_weight = True

    if not has_weight:
        return {'status': 'NO_POSITION', 'score': 0, 'msg': '纯现金无风险暴露'}

    # Beta 计算
    factor_rets = pca.transform(scaled_rets)
    betas = []
    for i in range(3):
        cov = np.cov(port_rets, factor_rets[:, i])[0, 1]
        var = np.var(factor_rets[:, i])
        beta = cov / var if var > 0 else 0.0
        betas.append(beta)

    # 集中度
    abs_betas = np.abs(betas)
    total_abs_beta = np.sum(abs_betas) + 1e-9
    concentration_ratios = abs_betas / total_abs_beta
    max_concentration = np.max(concentration_ratios)

    risk_flag = 'NORMAL'
    if max_concentration > 0.6:
        risk_flag = 'HIGH_CONCENTRATION'

    return {
        'asof': asof,
        'status': risk_flag,
        'betas': [round(b, 3) for b in betas],
        'concentration_pct': round(max_concentration * 100, 1),
        'explained_var': round(sum(pca.explained_variance_ratio_) * 100, 1),
        'msg': f"风险集中度 {max_concentration*100:.1f}% (PC{np.argmax(concentration_ratios)+1})"
    }

if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    w = {'BTC': 0.15, 'GOLD': 0.075, 'US10Y': 0.10}
    r = compute_factor_attribution(asof, w)
    print(f"\n{'='*60}")
    print(f"  因子归因 - {asof}")
    print(f"{'='*60}")
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print(f"{'='*60}\n")