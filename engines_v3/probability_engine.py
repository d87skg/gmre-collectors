# -*- coding: utf-8 -*-
"""engines_v3/probability_engine.py - 概率化输出（v5：修复双重惩罚过度问题）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
PRIORS = {'R0': 0.55, 'R1': 0.10, 'R2': 0.08, 'R3': 0.12, 'R4': 0.10, 'R5': 0.05}

def compute_likelihoods(z_scores):
    inf, mon, fis, liq, risk = z_scores.get('INF', 0), z_scores.get('MON', 0), z_scores.get('FIS', 0), z_scores.get('LIQ', 0), z_scores.get('RISK', 0)
    likelihoods = {
        'R0': np.exp(-0.15 * (inf**2 + mon**2 + fis**2 + liq**2 + risk**2)),
        'R1': np.exp(-0.25 * ((inf-2)**2 + (mon-1.5)**2 + risk**2)),
        'R2': np.exp(-0.25 * ((inf-2)**2 + (fis-2)**2 + (liq-1)**2)),
        'R3': np.exp(-0.25 * ((mon-2)**2 + (risk-2)**2 + (inf-0.5)**2)),
        'R4': np.exp(-0.25 * ((inf+1.5)**2 + (liq+2)**2 + (risk-2.5)**2)),
        'R5': np.exp(-0.25 * ((risk-3)**2 + (liq-2.5)**2 + (mon+0.5)**2))
    }
    for r in likelihoods: likelihoods[r] = max(likelihoods[r], 1e-8)
    return likelihoods

def compute_posteriors(likelihoods):
    posteriors = {}
    total = 0
    for regime in PRIORS:
        p = PRIORS[regime] * likelihoods.get(regime, 0)
        posteriors[regime] = p
        total += p
    return {r: p / total for r, p in posteriors.items()} if total > 0 else {r: 0 for r in PRIORS}

def apply_micro_penalty(posteriors: dict, asof: str) -> dict:
    """修复双重惩罚：如果 Fragility 和 Stress 高度相关，限制总体惩罚力度"""
    penalty_factor = 1.0
    reasons = []

    try:
        conn = sqlite3.connect(DB_PATH)
        stress_row = conn.execute("SELECT triggered_count FROM stress_overlay_v2 WHERE asof_date=?", (asof,)).fetchone()
        if stress_row and stress_row[0] >= 2:
            penalty_factor += 0.15 * stress_row[0]  # 从0.5降为0.15
            reasons.append(f"Stress={stress_row[0]}层")

        frag_row = conn.execute("SELECT fragility_score FROM fragility_engine WHERE asof_date=?", (asof,)).fetchone()
        if frag_row and frag_row[0] >= 65:
            penalty_factor += 0.2  # 从1.0降为0.2
            reasons.append(f"Frag={frag_row[0]:.1f}")
        conn.close()
    except: pass

    if penalty_factor <= 1.0: return posteriors

    adjusted = posteriors.copy()
    transferred = 0.0
    # 修复：最多砍掉 20% 的 R0/R1 概率，防止概率彻底失真
    cut_ratio = min(0.1 * (penalty_factor - 1.0), 0.20) 

    for r in ['R0', 'R1']:
        if adjusted.get(r, 0) > 0:
            cut = adjusted[r] * cut_ratio
            adjusted[r] -= cut
            transferred += cut

    if transferred > 0:
        adjusted['R4'] += transferred * 0.6
        adjusted['R5'] += transferred * 0.4

    total = sum(adjusted.values())
    adjusted = {k: v / total for k, v in adjusted.items()} if total > 0 else adjusted

    print(f"  ⚠️ [微观加压] 惩罚因子 x{penalty_factor:.2f} (砍比例: {cut_ratio*100:.0f}%)")
    return adjusted

def evaluate_probability(asof: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT engine_id, z_score FROM engine_latents WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)", conn)
    conn.close()
    z_scores = dict(zip(df['engine_id'], df['z_score']))
    if not z_scores: return {}

    likelihoods = compute_likelihoods(z_scores)
    posteriors = compute_posteriors(likelihoods)
    posteriors = apply_micro_penalty(posteriors, asof)

    result = {
        'asof': asof,
        'current': {r: round(p, 4) for r, p in posteriors.items()},
        'high_risk_prob': round(posteriors['R4'] + posteriors['R5'], 4)
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS probability_engine (asof_date TEXT PRIMARY KEY, p_r0 REAL, p_r1 REAL, p_r2 REAL, p_r3 REAL, p_r4 REAL, p_r5 REAL, high_risk_prob REAL, detail TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO probability_engine VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (asof, posteriors['R0'], posteriors['R1'], posteriors['R2'], posteriors['R3'], posteriors['R4'], posteriors['R5'], result['high_risk_prob'], json.dumps(result)))
    conn.commit(); conn.close()
    print(f"  高风险概率 P(R4+R5): {result['high_risk_prob']*100:.2f}%")
    return result