# -*- coding: utf-8 -*-
"""engines_v3/factor_attribution.py - 极简因子归因与集中度风险"""
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

DB_PATH = 'data/macro.db'

def _load_series(conn, sid, limit=60):
    try:
        df = pd.read_sql_query(
            f"SELECT timestamp AS dt, value FROM observations WHERE series_id=? ORDER BY timestamp DESC LIMIT ?",
            conn, params=(sid, limit)
        )
        if not df.empty:
            df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
            df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
            return df.sort_values('dt').set_index('dt')['value'].astype(float)
    except Exception:
        pass
    return pd.Series(dtype=float)

def compute_factor_attribution(asof: str, port_weights: dict) -> dict:
    """
    输入: 当前组合权重 {'BTC': 0.15, 'GOLD': 0.075, 'US10Y': 0.10}，其余视为现金。
    计算: 组合在三大宏观因子（利率、流动性、风险偏好）上的暴露。
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        # 获取跨资产收益率序列
        assets = {
            'DXY': _load_series(conn, 'DXY_PROXY', 60),
            'US10Y': _load_series(conn, 'YC10Y', 60),
            'SP500': _load_series(conn, 'SP500', 60),
            'GOLD': _load_series(conn, 'GOLD_PRICE', 60),
            'BTC': _load_series(conn, 'BTC_SPOT_PRICE_1H', 60),
        }
    finally:
        conn.close()

    # 对齐收益率矩阵
    rets = pd.DataFrame({k: v.pct_change() for k, v in assets.items() if len(v) > 0}).dropna()
    if len(rets) < 20:
        return {'status': 'INSUFFICIENT_DATA'}

    # 提取三大宏观因子 (PCA)
    scaler = StandardScaler()
    scaled_rets = scaler.fit_transform(rets)
    pca = PCA(n_components=3)
    pca.fit(scaled_rets)
    
    # 确保载荷矩阵的正负号具备经济学解释（锚定为主）
    # 这里极简处理：看第一主成分与 DXY 的相关性，如果是正，说明是流动性因子
    components = pca.components_
    
    # 假设：
    # 因子 0：Risk Appetite (与 SP500、BTC 高度正相关)
    # 因子 1：Interest Rate (与 US10Y 正相关)
    # 因子 2：Liquidity/USD (与 DXY 相关)
    
    # 计算当前组合的收益率
    # 假设现金收益率为 0
    port_rets = np.zeros(len(rets))
    has_weight = False
    for asset, weight in port_weights.items():
        if asset in rets.columns and weight > 0:
            port_rets += rets[asset].values * weight
            has_weight = True

    if not has_weight:
        return {'status': 'NO_POSITION', 'score': 0, 'msg': '纯现金无风险暴露'}

    # 计算组合在各因子上的 Beta
    factor_rets = pca.transform(scaled_rets)
    betas = []
    for i in range(3):
        cov = np.cov(port_rets, factor_rets[:, i])[0, 1]
        var = np.var(factor_rets[:, i])
        beta = cov / var if var > 0 else 0.0
        betas.append(beta)

    # 计算集中度 (如果某个 Beta 的绝对值占总绝对值的比例过高)
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
        'msg': f"组合风险集中在第 {np.argmax(concentration_ratios)+1} 主成分上 ({max_concentration*100:.1f}%)"
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