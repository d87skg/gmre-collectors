# -*- coding: utf-8 -*-
"""engines_v3/risk_budget_engine.py - 影子风险预算与动量过滤引擎
v5.9: BLACK 状态与 RED 等价拦截 + 资产级降级
"""
import sqlite3
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

DB_PATH = 'data/macro.db'

ASSETS = {
    'SP500': 'SP500',
    'GOLD': 'GOLD_PRICE',
    'BTC': 'BTC_SPOT_PRICE_1H',
    'SHY': 'SHY_PRICE',
    'TLT': 'TLT_PRICE',
    'WTI': 'WTI_OIL',
}

DEFENSIVE_ALLOWLIST = ('GOLD', 'SHY', 'TLT')
TRADING_DAYS = 252
BTC_KEY = 'BTC'
BTC_FFILL_THRESHOLD = 0.15

_SHADOW_META = {}


def get_shadow_meta():
    return dict(_SHADOW_META)


def get_pit_series(series_id, limit=252):
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    query = """
        SELECT date_str AS timestamp, value FROM (
            SELECT substr(obs_ts, 1, 10) AS date_str, value,
                   ROW_NUMBER() OVER (PARTITION BY substr(obs_ts, 1, 10) ORDER BY obs_ts DESC) AS rn
            FROM observations
            WHERE series_id = ? AND value IS NOT NULL
        ) WHERE rn = 1
        ORDER BY date_str DESC LIMIT ?
    """
    try:
        df = pd.read_sql_query(query, conn, params=(series_id, limit))
        if df.empty:
            return pd.Series(dtype=float), 0
        raw_count = len(df)
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
        df = df.dropna(subset=['timestamp'])
        df = df.sort_values('timestamp').set_index('timestamp')['value'].astype(float)
        return df, raw_count
    except Exception as e:
        print(f"  ❌ [{series_id}] 取数失败: {e}")
        return pd.Series(dtype=float), 0
    finally:
        conn.close()


def estimate_covariance(returns):
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 60:
        return None, f"INSUFFICIENT_DATA (n={len(returns)} < 60)"
    lw = LedoitWolf()
    try:
        lw.fit(returns)
        cov = lw.covariance_
        min_eig = np.min(np.real(np.linalg.eigvals(cov)))
        if min_eig < 0:
            cov += (abs(min_eig) + 1e-8) * np.eye(len(returns.columns))
            return cov, f"FIXED_PSD (min_eig={min_eig:.2e})"
        is_sym = np.allclose(cov, cov.T, atol=1e-10)
        is_psd = min_eig >= -1e-10
        return cov, f"OK (n={len(returns)}, min_eig={min_eig:.2e}, sym={is_sym}, psd={is_psd})"
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

    multipliers = {"STRONG": 1.00, "NEUTRAL": 0.85, "WEAK": 0.50, "EXTREME_WEAK": 0.20}
    mult = multipliers[state]
    if state == "EXTREME_WEAK" and asset_class in ("BTC", "SP500", "WTI"):
        mult = 0.0
    return mult, state


def _validate_risk_math(cov, weights_arr, assets_order):
    n = len(assets_order)
    assert cov.shape == (n, n), f"cov.shape={cov.shape} != ({n},{n})"
    assert np.allclose(cov, cov.T, atol=1e-10), "协方差矩阵不对称"
    weights_arr = np.asarray(weights_arr, dtype=float)
    portfolio_var = float(weights_arr @ cov @ weights_arr)
    assert portfolio_var >= -1e-12, f"组合方差为负: {portfolio_var}"
    portfolio_vol_daily = float(np.sqrt(max(portfolio_var, 0.0)))
    asset_vol_daily = np.sqrt(np.maximum(np.diag(cov), 0.0))
    asset_vol_annual = asset_vol_daily * np.sqrt(TRADING_DAYS)
    portfolio_vol_annual = portfolio_vol_daily * np.sqrt(TRADING_DAYS)
    if portfolio_vol_daily > 0:
        mrc = (cov @ weights_arr) / portfolio_vol_daily
        rc = weights_arr * mrc
    else:
        mrc = np.zeros(n); rc = np.zeros(n)
    rc_sum = float(np.sum(rc))
    upper_bound = float(np.sum(weights_arr * asset_vol_annual))
    return {
        "portfolio_vol_daily": portfolio_vol_daily,
        "portfolio_vol_annual": portfolio_vol_annual,
        "asset_vol_daily": asset_vol_daily,
        "asset_vol_annual": asset_vol_annual,
        "mrc": mrc, "rc": rc, "rc_sum": rc_sum, "upper_bound": upper_bound,
    }


def _build_aligned_returns(prices_dict):
    non_btc_names = [n for n in prices_dict if n != BTC_KEY]
    evidence = {
        'align_method': 'FALLBACK',
        'btc_source_timestamp_count': 0,
        'btc_resampled_count': 0,
        'btc_weekend_aggregated_count': 0,
        'btc_missing_source_count': 0,
        'btc_forward_fill_count': 0,
        'btc_forward_fill_ratio': 0.0,
        'btc_max_gap_hours': 0.0,
        'price_cutoff_verified': False,
    }

    if BTC_KEY not in prices_dict or len(non_btc_names) < 4:
        df = pd.DataFrame(prices_dict).dropna()
        returns = df.pct_change().dropna()
        evidence['align_method'] = 'FALLBACK_NO_BTC_OR_INSUFFICIENT'
        return returns, evidence, True

    non_btc_df = pd.DataFrame({n: prices_dict[n] for n in non_btc_names}).dropna()
    skeleton = non_btc_df.index

    btc_series = prices_dict[BTC_KEY].copy()
    evidence['btc_source_timestamp_count'] = int(len(btc_series))

    has_hourly = any(ts.hour != 0 or ts.minute != 0 for ts in btc_series.index[:24])
    evidence['price_cutoff_verified'] = not has_hourly

    btc_daily = btc_series.copy()
    btc_daily.index = btc_daily.index.normalize()
    btc_daily = btc_daily.groupby(level=0).last()

    btc_aligned = btc_daily.reindex(skeleton, method='ffill')
    evidence['btc_resampled_count'] = int(len(btc_aligned))

    skeleton_dates_set = set(pd.Index(skeleton).normalize())
    btc_dates_set = set(btc_daily.index)
    missing_dates = skeleton_dates_set - btc_dates_set
    evidence['btc_forward_fill_count'] = int(len(missing_dates))
    evidence['btc_missing_source_count'] = int(len(missing_dates))
    evidence['btc_forward_fill_ratio'] = (
        float(len(missing_dates) / len(btc_aligned)) if len(btc_aligned) > 0 else 0.0
    )

    gaps_in_days = pd.Series(skeleton).diff().dt.days
    weekend_gaps = (gaps_in_days > 1).sum()
    evidence['btc_weekend_aggregated_count'] = int(weekend_gaps)

    if len(skeleton) > 1:
        max_gap_hours = float(pd.Series(skeleton).diff().dt.total_seconds().max() / 3600)
        evidence['btc_max_gap_hours'] = max_gap_hours

    aligned_prices = non_btc_df.copy()
    aligned_prices[BTC_KEY] = btc_aligned
    aligned_prices = aligned_prices.dropna()

    if len(aligned_prices) < 60:
        evidence['align_method'] = 'INSUFFICIENT_AFTER_ALIGN'
        return aligned_prices.pct_change().dropna(), evidence, False

    evidence['align_method'] = 'SYNC_ALIGNED'
    btc_covariance_eligible = evidence['btc_forward_fill_ratio'] <= BTC_FFILL_THRESHOLD

    returns = aligned_prices.pct_change().dropna()

    if not btc_covariance_eligible:
        returns = returns.drop(columns=[BTC_KEY])
        print(f"  🚨 [资产级降级] BTC forward-fill 比例 {evidence['btc_forward_fill_ratio']*100:.1f}% "
              f"> {BTC_FFILL_THRESHOLD*100:.0f}%，BTC 从协方差矩阵中剔除")

    return returns, evidence, btc_covariance_eligible


def compute_shadow_weights(gate_state, event_perm="PROCEED", stress_overall=""):
    global _SHADOW_META
    _SHADOW_META = {}

    print("\n🔮 [Shadow Mode] 正在计算风险预算与动量过滤...")

    # 🆕 修复点 1：BLACK 与 RED 等价
    print("\n  🛡️ [EXECUTION AUTHORIZATION]")
    for asset in ASSETS.keys():
        if event_perm == "BLOCK" or gate_state in ("RED", "BLACK"):
            if asset in DEFENSIVE_ALLOWLIST:
                print(f"    {asset:<6}: 允许(白名单) | 原因: {event_perm}_DEFENSIVE_ALLOWLIST")
            else:
                print(f"    {asset:<6}: 禁止(新增) | 原因: {event_perm}_DENY")
        else:
            print(f"    {asset:<6}: 允许(按预算) | 原因: {event_perm}")

    prices = {}
    date_ranges = {}
    per_asset_diag = {}
    for name, sid in ASSETS.items():
        s, raw_count = get_pit_series(sid, limit=252)
        if not s.empty:
            prices[name] = s
            idx = s.index
            unique_count = len(idx.unique())
            duplicate_count = len(idx) - unique_count
            date_ranges[name] = (str(idx[0])[:10], str(idx[-1])[:10], len(s))
            per_asset_diag[name] = {
                'raw_count': raw_count,
                'unique_date_count': unique_count,
                'duplicate_date_count': duplicate_count,
                'sample_count': len(s),
            }

    if len(prices) < 4:
        print(f"  ❌ 有效资产不足 ({len(prices)}/6)，影子计算终止。")
        return None

    print("\n  📋 [协方差输入诊断]")
    print(f"  {'资产':<8} | {'样本数':<6} | {'唯一日期':<8} | {'重复':<4} | {'首日':<12} | {'末日':<12}")
    print("  " + "-" * 70)
    for name, (d0, d1, n) in date_ranges.items():
        diag = per_asset_diag[name]
        print(f"  {name:<8} | {n:<6} | {diag['unique_date_count']:<8} | "
              f"{diag['duplicate_date_count']:<4} | {d0:<12} | {d1:<12}")

    returns, align_evidence, btc_covariance_eligible = _build_aligned_returns(prices)

    assert returns.index.is_unique, "❌ 收益率索引不唯一"
    assert returns.notna().all().all(), "❌ 收益率含 NaN"
    assert returns.index.is_monotonic_increasing, "❌ 收益率索引非单调递增"

    common_date_count = len(returns)
    common_coverage = common_date_count / 252.0

    print(f"\n  ⚠️ [真实收益区间对齐]")
    print(f"    RETURN_INTERVAL_ALIGNMENT    : {align_evidence['align_method']}")
    print(f"    PAIRWISE_VALID_OBSERVATIONS  : {common_date_count}")
    print(f"    COMMON_DATE_COVERAGE         : {common_coverage*100:.1f}%")

    print(f"\n  🕐 [BTC_ALIGNMENT_AUDIT]")
    print(f"    SOURCE_TIMESTAMP_COUNT       : {align_evidence['btc_source_timestamp_count']}")
    print(f"    RESAMPLED_TIMESTAMP_COUNT    : {align_evidence['btc_resampled_count']}")
    print(f"    WEEKEND_AGGREGATED_COUNT     : {align_evidence['btc_weekend_aggregated_count']}")
    print(f"    MISSING_SOURCE_TIMESTAMP_CNT : {align_evidence['btc_missing_source_count']}")
    print(f"    FORWARD_FILL_COUNT           : {align_evidence['btc_forward_fill_count']}")
    print(f"    FORWARD_FILL_RATIO           : {align_evidence['btc_forward_fill_ratio']*100:.1f}%")
    print(f"    MAX_GAP_HOURS                : {align_evidence['btc_max_gap_hours']:.1f}h")
    print(f"    PRICE_CUTOFF_VERIFIED        : {align_evidence['price_cutoff_verified']}")
    print(f"    BTC_COVARIANCE_ELIGIBLE      : {btc_covariance_eligible}")

    if not btc_covariance_eligible:
        print(f"    🚨 BTC_FORWARD_FILL_WARNING   : >15% 触发资产级降级，BTC 不参与协方差")
    elif align_evidence['btc_forward_fill_ratio'] > 0.05:
        print(f"    ⚠️ BTC_FORWARD_FILL_WARNING   : >5% 需关注")

    degenerate = [col for col in returns.columns if returns[col].std() < 1e-10]
    if degenerate:
        print(f"  🚨 [退化资产] 以下资产收益率标准差≈0: {degenerate}")

    assets_order = list(returns.columns)
    cov, cov_status = estimate_covariance(returns)
    print(f"  [协方差] 状态: {cov_status} | Ledoit-Wolf 收缩完成")
    if cov is None:
        return None

    asset_vol_daily = np.sqrt(np.maximum(np.diag(cov), 0.0))
    vols_series = pd.Series(asset_vol_daily, index=assets_order)
    vols_for_rp = vols_series.replace(0, np.nan).fillna(1e-6)
    inv_vols = 1.0 / vols_for_rp
    inv_vols = inv_vols.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    total_inv_vol = inv_vols.sum()
    if total_inv_vol <= 0:
        base_weights = pd.Series(1.0 / len(assets_order), index=assets_order)
    else:
        base_weights = inv_vols / total_inv_vol

    # 🆕 修复点 2：BLACK 与 RED 等价
    if gate_state in ("RED", "BLACK") or event_perm in ("REDUCE", "BLOCK"):
        max_capital_exposure = 0.40
    elif gate_state == "ORANGE":
        max_capital_exposure = 0.50
    else:
        max_capital_exposure = 0.70

    liquidity_constrained = 'LIQUIDITY_BUFFER_DEPLETION' in (stress_overall or '')
    previous_cap = max_capital_exposure
    if liquidity_constrained and max_capital_exposure > 0.35:
        print(f"  🚨 [流动性挤兑约束] Stress 含 LIQUIDITY_BUFFER_DEPLETION，"
              f"资本敞口上限从 {max_capital_exposure*100:.1f}% 强制压至 35.0%")
        max_capital_exposure = 0.35

    print(f"  ⚙️ [风控约束] Gate={gate_state}, Event={event_perm}, Stress={stress_overall or 'NONE'} "
          f"-> 资本敞口上限 {max_capital_exposure*100:.1f}%")

    w_theoretical = {a: base_weights[a] * max_capital_exposure for a in assets_order}
    pre_filter_exposure = sum(w_theoretical.values())

    w_after_permission = {}
    for a in assets_order:
        # 🆕 修复点 3：BLACK 与 RED 等价
        if (gate_state in ("RED", "BLACK") or event_perm in ("REDUCE", "BLOCK")) and a not in DEFENSIVE_ALLOWLIST:
            w_after_permission[a] = 0.0
        else:
            w_after_permission[a] = w_theoretical[a]
    post_permission_exposure = sum(w_after_permission.values())

    w_after_momentum = {}
    momentum_states = {}
    for a in assets_order:
        if w_after_permission[a] > 0:
            mult, state = momentum_multiplier(prices[a], a)
            w_after_momentum[a] = w_after_permission[a] * mult
            momentum_states[a] = (state, mult)
        else:
            w_after_momentum[a] = 0.0
            momentum_states[a] = ("BLOCKED", 0.0)
    post_momentum_exposure = sum(w_after_momentum.values())

    final_weights = {a: min(w_after_momentum[a], 0.15) for a in assets_order}
    pre_scale_exposure = sum(final_weights.values())

    if pre_scale_exposure > max_capital_exposure:
        scale_down = max_capital_exposure / pre_scale_exposure
        for k in final_weights:
            final_weights[k] *= scale_down
        final_exposure = max_capital_exposure
        print(f"  ⚠️ [敞口兜底] 硬缩放 (x{scale_down:.3f})")
    else:
        final_exposure = pre_scale_exposure

    unallocated_budget = max(0.0, max_capital_exposure - final_exposure)
    cash_weight = 1.0 - final_exposure

    print(f"\n  📊 [资本敞口六层语义]")
    print(f"    MAX_CAPITAL_EXPOSURE     : {max_capital_exposure*100:.2f}%")
    print(f"    PRE_FILTER_EXPOSURE      : {pre_filter_exposure*100:.2f}%")
    print(f"    POST_PERMISSION_EXPOSURE : {post_permission_exposure*100:.2f}%")
    print(f"    POST_MOMENTUM_EXPOSURE   : {post_momentum_exposure*100:.2f}%")
    print(f"    FINAL_CAPITAL_EXPOSURE   : {final_exposure*100:.2f}%")
    print(f"    UNALLOCATED_BUDGET       : {unallocated_budget*100:.2f}%")

    print(f"\n  {'资产':<8} | {'基础权重':<10} | {'动量':<12} | {'乘数':<6} | {'目标权重':<10}")
    print("  " + "-" * 65)
    for a in assets_order:
        w_base = base_weights[a]
        state, mult = momentum_states.get(a, ("N/A", 0.0))
        print(f"  {a:<8} | {w_base*100:>8.2f}% | {state:<12} | {mult:<6.2f} | {final_weights[a]*100:>8.2f}%")

    print("  " + "-" * 65)
    print(f"  💰 [目标仓位汇总] 现金底线: {cash_weight*100:.1f}% (资本敞口: {final_exposure*100:.1f}%)")
    for k, v in final_weights.items():
        if v > 0:
            print(f"     - {k}: {v*100:.2f}%")

    print("\n  📊 [风险贡献诊断 - 严格真实交易日口径]")
    try:
        weights_arr = np.array([final_weights.get(col, 0.0) for col in assets_order], dtype=float)
        diag = _validate_risk_math(cov, weights_arr, assets_order)
        rc_share = diag["rc"] / diag["rc_sum"] * 100 if diag["rc_sum"] > 0 else np.zeros_like(diag["rc"])

        print(f"  {'资产':<8} | {'权重':<8} | {'年化波动':<10} | {'MRC(日)':<10} | {'RC占比':<8}")
        print("  " + "-" * 60)
        for i, a in enumerate(assets_order):
            print(f"  {a:<8} | {weights_arr[i]*100:>6.2f}% | "
                  f"{diag['asset_vol_annual'][i]*100:>8.2f}% | "
                  f"{diag['mrc'][i]:>10.6f} | {rc_share[i]:>6.1f}%")

        print(f"\n  组合日波动率      : {diag['portfolio_vol_daily']:.6f} ({diag['portfolio_vol_daily']*100:.4f}%)")
        print(f"  组合年化波动率    : {diag['portfolio_vol_annual']:.6f} ({diag['portfolio_vol_annual']*100:.2f}%)")
        print(f"  RC 总和校验       : {diag['rc_sum']:.6f} (应等于组合日波动率 {diag['portfolio_vol_daily']:.6f})")
        print(f"  RC占比总和校验    : {np.sum(rc_share):.2f}%")

        print(f"\n  🎯 [波动率预算状态]")
        print(f"    TARGET_VOLATILITY            : N/A (未实施)")
        print(f"    REALIZED_EST_VOLATILITY      : {diag['portfolio_vol_annual']*100:.2f}%")
        print(f"    TARGET_VOLATILITY_DESIGN_STATUS : NOT_IMPLEMENTED (资本敞口 ≠ 波动率预算)")

        market_eigvals, market_eigvecs = np.linalg.eigh(cov)
        market_pc1_share = market_eigvals[-1] / np.sum(market_eigvals) if np.sum(market_eigvals) > 0 else 0.0
        market_pc1_loadings = market_eigvecs[:, -1]

        held_mask = weights_arr > 1e-12
        if np.sum(held_mask) > 1:
            held_indices = np.where(held_mask)[0]
            held_cov = cov[np.ix_(held_indices, held_indices)]
            held_assets = [assets_order[i] for i in held_indices]
            held_eigvals, held_eigvecs = np.linalg.eigh(held_cov)
            portfolio_pc1_share = held_eigvals[-1] / np.sum(held_eigvals) if np.sum(held_eigvals) > 0 else 0.0
            portfolio_pc1_loadings = held_eigvecs[:, -1]
        else:
            portfolio_pc1_share = 0.0
            portfolio_pc1_loadings = None
            held_assets = []

        print(f"\n  📐 [PC1 风险结构 - 双口径分离]")
        print(f"    A. MARKET_PC1_EXPLAINED_VARIANCE    : {market_pc1_share*100:.1f}%")
        print(f"    B. PORTFOLIO_PC1_RISK_SHARE         : {portfolio_pc1_share*100:.1f}%")

        print(f"\n    [A. 市场 PC1 载荷 (协方差池资产)]")
        print(f"    {'资产':<8} | {'PC1 载荷':<10}")
        print("    " + "-" * 28)
        for i, a in enumerate(assets_order):
            print(f"    {a:<8} | {market_pc1_loadings[i]:>+10.4f}")

        if held_assets:
            print(f"\n    [B. 组合 PC1 载荷 (仅持仓资产)]")
            print(f"    {'资产':<8} | {'PC1 载荷':<10}")
            print("    " + "-" * 28)
            for i, a in enumerate(held_assets):
                print(f"    {a:<8} | {portfolio_pc1_loadings[i]:>+10.4f}")

        _SHADOW_META.update({
            'gate_state': gate_state,
            'max_capital_exposure': max_capital_exposure,
            'previous_cap': previous_cap,
            'pre_filter_exposure': pre_filter_exposure,
            'post_permission_exposure': post_permission_exposure,
            'post_momentum_exposure': post_momentum_exposure,
            'final_capital_exposure': final_exposure,
            'unallocated_budget': unallocated_budget,
            'cash_weight': cash_weight,
            'common_date_count': common_date_count,
            'common_coverage': common_coverage,
            'return_align_evidence': align_evidence,
            'btc_covariance_eligible': btc_covariance_eligible,
            'market_pc1_share': float(market_pc1_share),
            'portfolio_pc1_share': float(portfolio_pc1_share),
            'market_pc1_loadings': {a: float(market_pc1_loadings[i]) for i, a in enumerate(assets_order)},
            'portfolio_pc1_loadings': {a: float(portfolio_pc1_loadings[i]) for i, a in enumerate(held_assets)} if held_assets else {},
            'per_asset_diag': per_asset_diag,
            'cov_status': cov_status,
            'realized_est_volatility': float(diag['portfolio_vol_annual']),
            'target_volatility': None,
            'btc_forward_fill_ratio': align_evidence['btc_forward_fill_ratio'],
            'btc_forward_fill_count': align_evidence['btc_forward_fill_count'],
        })

    except Exception as e:
        print(f"    ⚠️ 风险贡献计算或校验失败: {e}")

    return final_weights


if __name__ == "__main__":
    compute_shadow_weights("RED", "BLOCK", "LIQUIDITY_BUFFER_DEPLETION + USD_CREDIT_DEGRADATION")