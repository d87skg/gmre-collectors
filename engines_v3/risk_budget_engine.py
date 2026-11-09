# -*- coding: utf-8 -*-
"""engines_v3/risk_budget_engine.py - 影子风险预算与动量过滤引擎 (v3.2: 短债SHY适配)"""
import sqlite3
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

DB_PATH = 'data/macro.db'

# 🆕 资产替换：用 SHY 替代 US10Y
ASSETS = {
    'SP500': 'SP500',
    'GOLD': 'GOLD_PRICE',
    'BTC': 'BTC_SPOT_PRICE_1H',
    'SHY': 'SHY_PRICE'
}

def get_pit_series(series_id, limit=252):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    query = """
        SELECT timestamp, value 
        FROM observations 
        WHERE series_id = ? AND value IS NOT NULL
        ORDER BY timestamp ASC LIMIT ?
    """
    try:
        df = pd.read_sql_query(query, conn, params=(series_id, limit * 2))
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df['date'] = df['timestamp'].dt.date
        df = df.drop_duplicates(subset=['date'], keep='last')
        df = df.sort_values('date').set_index('date')['value'].astype(float)
        return df.ffill().tail(limit)
    except Exception:
        return pd.Series(dtype=float)
    finally:
        conn.close()

def estimate_covariance(returns):
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 60:
        return None, "INSUFFICIENT_DATA"
    
    lw = LedoitWolf()
    try:
        lw.fit(returns)
        cov = lw.covariance_
        min_eig = np.min(np.real(np.linalg.eigvals(cov)))
        if min_eig < 0:
            cov += (abs(min_eig) + 1e-8) * np.eye(len(returns.columns))
            return cov, "FIXED_PSD"
        return cov, "OK"
    except Exception as e:
        return None, f"COV_ERROR: {e}"

def momentum_multiplier(series, asset_class):
    if len(series) < 60:
        return 0.85, "NEUTRAL"
        
    latest = series.iloc[-1]
    ret_20d = (latest / series.iloc[-20]) - 1 if len(series) >= 20 else 0
    ret_60d = (latest / series.iloc[-60]) - 1 if len(series) >= 60 else 0
    
    vol_20d = series.pct_change().tail(20).std()
    vol_60d = series.pct_change().tail(60).std()
    is_vol_spike = vol_20d > (vol_60d * 1.5)
    
    state = "NEUTRAL"
    if ret_20d < 0 and ret_60d < 0 and is_vol_spike:
        state = "EXTREME_WEAK"
    elif ret_20d < 0 and ret_60d < 0:
        state = "WEAK"
    elif ret_20d > 0 and ret_60d > 0 and not is_vol_spike:
        state = "STRONG"
        
    multipliers = {
        "STRONG": 1.00, "NEUTRAL": 0.85, "WEAK": 0.50, "EXTREME_WEAK": 0.20
    }
    mult = multipliers[state]
    if state == "EXTREME_WEAK" and asset_class in ("BTC", "SP500"):
        mult = 0.0
            
    return mult, state

def compute_shadow_weights(gate_state):
    print("\n🔮 [Shadow Mode] 正在计算风险预算与动量过滤...")
    
    prices = {}
    for name, sid in ASSETS.items():
        s = get_pit_series(sid, limit=252)
        if not s.empty:
            prices[name] = s
            
    if len(prices) < 3:
        print("  ❌ 有效资产不足，影子计算终止。")
        return None
        
    df_prices = pd.DataFrame(prices).ffill().dropna()
    
    # 🆕 由于 SHY 是 ETF 价格，统一用 pct_change 计算收益率
    returns = df_prices.pct_change().dropna()
    
    cov, cov_status = estimate_covariance(returns)
    print(f"  [协方差] 状态: {cov_status} | 形状: {cov.shape if cov is not None else 'None'}")
    if cov is None: return None
    
    vols = returns.std()
    vols = vols.replace(0, np.nan).fillna(0.02)
    
    inv_vols = 1 / vols
    inv_vols = inv_vols.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    
    total_inv_vol = inv_vols.sum()
    if total_inv_vol <= 0:
        base_weights = pd.Series(1.0 / len(returns.columns), index=returns.columns)
    else:
        base_weights = inv_vols / total_inv_vol
    
    final_weights = {}
    print(f"\n  {'资产':<8} | {'基础RP权重':<10} | {'动量状态':<12} | {'乘数':<6} | {'最终权重(防放大)':<10}")
    print("  " + "-"*65)
    
    for asset in base_weights.index:
        w_base = base_weights[asset]
        
        if gate_state == "RED" and asset in ("BTC", "SP500"):
            final_weights[asset] = 0.0
            print(f"  {asset:<8} | {w_base*100:>8.2f}% | {'RED禁止':<12} | 0.00   |   0.00%")
            continue
            
        mult, state = momentum_multiplier(df_prices[asset], asset)
        w_adjusted = w_base * mult
        
        target_risk_budget = 0.30 if gate_state == "RED" else 0.70
        w_target_absolute = w_adjusted * target_risk_budget
        w_final = min(w_target_absolute, w_base)
        
        final_weights[asset] = w_final
        print(f"  {asset:<8} | {w_base*100:>8.2f}% | {state:<12} | {mult:<6.2f} | {w_final*100:>8.2f}%")
        
    total_allocated = sum(final_weights.values())
    cash_weight = 1.0 - total_allocated
    
    print("  " + "-"*65)
    print(f"  💰 [目标仓位汇总] 现金底线: {cash_weight*100:.1f}% (风险敞口: {total_allocated*100:.1f}%)")
    for k, v in final_weights.items():
        if v > 0:
            print(f"     - {k}: {v*100:.1f}%")
            
    return final_weights

if __name__ == "__main__":
    compute_shadow_weights("RED")