# -*- coding: utf-8 -*-
"""tools/audit_multi_source_divergence.py - 主备源差异审计（v4: 修 bug + 简化判定）"""
import sys, os, sqlite3
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from core import units

DB_PATH = 'data/macro.db'

THRESHOLDS = {
    'FEDFUNDS': {
        'kind': 'rate',
        'mae_max': 0.05,
        'corr_min': 0.85,
        'decision_levels': [3.5, 4.5],
    },
    'DXY_PROXY': {
        'kind': 'index',
        'mae_max': 1.0,
        'corr_min': 0.95,
        'decision_levels': [100, 110],
    },
    'BTC_SPOT_PRICE_1H': {
        'kind': 'price',
        'mae_pct_max': 0.05,
        'pct_change_corr_min': 0.90,
        'decision_levels': [50000],
    },
    'WTI_OIL': {
        'kind': 'price',
        'mae_pct_max': 0.05,
        'pct_change_corr_min': 0.90,
        'decision_levels': [80, 100],
    },
    'GOLD_PRICE': {
        'kind': 'price',
        'mae_pct_max': 0.05,
        'pct_change_corr_min': 0.90,
        'decision_levels': [2000, 4000],
    },
}


def compare_sources(series_id, limit=252):
    cid, entry = units.entry_of(series_id)
    # 只审计 canonical 指标本身，跳过别名
    if series_id != cid:
        return

    candidates = units.candidates_of(series_id)
    cfg = THRESHOLDS.get(series_id, {'kind': 'default', 'mae_max': 0.05, 'corr_min': 0.9})

    print(f"\n{'='*70}")
    print(f"  审计指标: {series_id}  (类型: {cfg['kind']})")
    print(f"  候选源  : {candidates}")
    print(f"{'='*70}")

    conn = sqlite3.connect(DB_PATH)
    series_dict = {}
    for cand in candidates:
        try:
            df = pd.read_sql_query(
                "SELECT substr(obs_ts,1,10) AS dt, value FROM observations "
                "WHERE series_id=? ORDER BY obs_ts DESC LIMIT ?",
                conn, params=(cand, limit)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'])
                df = df.drop_duplicates(subset='dt').set_index('dt')['value'].astype(float)
                df = df.sort_index()
                series_dict[cand] = df
        except Exception:
            pass
    conn.close()

    if len(series_dict) < 2:
        print(f"  ⚠️ 有效源不足 2 个（仅有: {list(series_dict.keys())}）")
        return

    sources = sorted(series_dict.items(), key=lambda x: x[1].index[-1], reverse=True)
    primary_name, primary = sources[0]
    backup_name, backup = sources[1]

    print(f"  主源: {primary_name}  (最新: {primary.index[-1].date()}, 值: {primary.iloc[-1]:.4f})")
    print(f"  备源: {backup_name}  (最新: {backup.index[-1].date()}, 值: {backup.iloc[-1]:.4f})")

    joined = pd.DataFrame({primary_name: primary, backup_name: backup}).dropna()
    if joined.empty:
        print(f"  ⚠️ 两个源无共同日期")
        return

    diff = joined[primary_name] - joined[backup_name]
    print(f"  共同样本数: {len(joined)}")

    # ===== 按类型判定 =====
    if cfg['kind'] == 'price':
        rel_diff = float((diff.abs() / joined[backup_name].abs()).mean())

        # 对比 pct_change（下游引擎真正用的）
        pct_p = joined[primary_name].pct_change().dropna()
        pct_b = joined[backup_name].pct_change().dropna()
        aligned = pd.DataFrame({'p': pct_p, 'b': pct_b}).dropna()

        if len(aligned) > 2:
            pct_corr = float(aligned['p'].corr(aligned['b']))
        else:
            pct_corr = 0.0

        print(f"  MAE(相对): {rel_diff*100:.2f}%")
        print(f"  pct_change 共同样本: {len(aligned)}")
        print(f"  pct_change 相关系数: {pct_corr:.4f}")

        ok = (rel_diff <= cfg['mae_pct_max']) and (pct_corr >= cfg['pct_change_corr_min'])

    else:
        mae = float(diff.abs().mean())
        corr = float(joined[primary_name].corr(joined[backup_name])) if len(joined) > 2 else 0.0

        print(f"  MAE: {mae:.4f}")
        print(f"  相关系数: {corr:.4f}")

        ok = (mae <= cfg['mae_max']) and (corr >= cfg['corr_min'])

    # 决策阈值检查
    p_latest = float(primary.iloc[-1])
    b_latest = float(backup.iloc[-1])
    threshold_breached = False
    for th in cfg.get('decision_levels', []):
        if (p_latest > th) != (b_latest > th):
            print(f"  🚨 [决策突变] 主源({p_latest:.4f}) 和 备源({b_latest:.4f}) 分居阈值 {th} 两侧")
            threshold_breached = True

    if not ok:
        print(f"  ❌ [不通过] 差异超出容忍上限")
    elif threshold_breached:
        print(f"  🟡 [有条件通过] 差异在容忍内，但跨越决策阈值")
    else:
        print(f"  ✅ [通过] 差异在容忍内，切换安全")


if __name__ == "__main__":
    for sid in ['FEDFUNDS', 'DXY_PROXY', 'BTC_SPOT_PRICE_1H', 'WTI_OIL', 'GOLD_PRICE']:
        compare_sources(sid)
    print(f"\n{'='*70}\n  审计完成\n{'='*70}")