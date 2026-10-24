"""engines_v3/probability_engine.py - 概率化输出（贝叶斯平滑稳定版）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

PRIORS = {
    'R0': 0.55, 'R1': 0.10, 'R2': 0.08, 'R3': 0.12, 'R4': 0.10, 'R5': 0.05,
}

def compute_likelihoods(z_scores):
    """基于Z-score计算各regime的似然度"""
    inf = z_scores.get('INF', 0)
    mon = z_scores.get('MON', 0)
    fis = z_scores.get('FIS', 0)
    liq = z_scores.get('LIQ', 0)
    risk = z_scores.get('RISK', 0)

    likelihoods = {}
    
    # 为了避免过度压缩，我们将指数惩罚系数减半，并限制最大距离
    likelihoods['R0'] = np.exp(-0.15 * (inf**2 + mon**2 + fis**2 + liq**2 + risk**2))
    likelihoods['R1'] = np.exp(-0.25 * ((inf-2)**2 + (mon-1.5)**2 + risk**2))
    likelihoods['R2'] = np.exp(-0.25 * ((inf-2)**2 + (fis-2)**2 + (liq-1)**2))
    likelihoods['R3'] = np.exp(-0.25 * ((mon-2)**2 + (risk-2)**2 + (inf-0.5)**2))
    likelihoods['R4'] = np.exp(-0.25 * ((inf+1.5)**2 + (liq+2)**2 + (risk-2.5)**2))
    likelihoods['R5'] = np.exp(-0.25 * ((risk-3)**2 + (liq-2.5)**2 + (mon+0.5)**2))

    # 防下溢保护：拉普拉斯平滑，不允许出现绝对的 0 概率
    for r in likelihoods:
        likelihoods[r] = max(likelihoods[r], 1e-8)
        
    return likelihoods

def compute_posteriors(likelihoods):
    """贝叶斯更新：prior × likelihood → posterior"""
    posteriors = {}
    total = 0
    for regime in PRIORS:
        p = PRIORS[regime] * likelihoods.get(regime, 0)
        posteriors[regime] = p
        total += p

    if total == 0:
        return {r: 0 for r in PRIORS}

    return {r: p / total for r, p in posteriors.items()}

def evaluate_probability(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Probability Engine - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("""
            SELECT engine_id, z_score FROM engine_latents
            WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)
        """, conn)
        z_scores = dict(zip(df['engine_id'], df['z_score']))
    finally:
        conn.close()

    if not z_scores:
        print("  ⚠️ 无五引擎数据")
        return {}

    print(f"  当前Z-score: {z_scores}\n")

    likelihoods = compute_likelihoods(z_scores)
    print("[1/2] 似然度 P(Data|Regime) (采用平滑防下溢)：")
    for r, l in sorted(likelihoods.items()):
        print(f"    {r}: {l:.8e}")

    posteriors = compute_posteriors(likelihoods)

    print(f"\n  🔍 [审计中间变量] 先验 / 似然 / 后验")
    print(f"    {'State':<4} | {'Prior':<8} | {'Likelihood':<14} | {'Posterior':<10}")
    print(f"    {'-'*4} | {'-'*8} | {'-'*14} | {'-'*10}")
    for r in sorted(PRIORS.keys()):
        prior = PRIORS[r]
        lik = likelihoods.get(r, 0.0)
        post = posteriors.get(r, 0.0) * 100
        print(f"    {r:<4} | {prior:<8.3f} | {lik:<14.8e} | {post:>8.4f}%")

    print(f"\n[2/2] 后验概率：")
    for r in sorted(posteriors.keys()):
        bar = '█' * int(posteriors[r] * 50)
        print(f"    P({r}) = {posteriors[r]*100:7.4f}% {bar}")

    future_1w = {}
    future_1m = {}
    for r, p in posteriors.items():
        future_1w[r] = p * 0.95 + PRIORS[r] * 0.05
        future_1m[r] = p * 0.85 + PRIORS[r] * 0.15

    total_1w = sum(future_1w.values())
    total_1m = sum(future_1m.values())
    future_1w = {r: p/total_1w for r, p in future_1w.items()}
    future_1m = {r: p/total_1m for r, p in future_1m.items()}

    result = {
        'asof': asof,
        'current': {r: round(p, 4) for r, p in posteriors.items()},
        'future_1w': {r: round(p, 4) for r, p in future_1w.items()},
        'future_1m': {r: round(p, 4) for r, p in future_1m.items()},
        'high_risk_prob': round(posteriors['R4'] + posteriors['R5'], 4)
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS probability_engine (
            asof_date TEXT PRIMARY KEY,
            p_r0 REAL, p_r1 REAL, p_r2 REAL, p_r3 REAL, p_r4 REAL, p_r5 REAL,
            high_risk_prob REAL, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO probability_engine
        (asof_date, p_r0, p_r1, p_r2, p_r3, p_r4, p_r5, high_risk_prob, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (asof, posteriors['R0'], posteriors['R1'], posteriors['R2'],
          posteriors['R3'], posteriors['R4'], posteriors['R5'],
          result['high_risk_prob'], json.dumps(result)))
    conn.commit()
    conn.close()

    print(f"\n  高风险概率 (R4+R5): {result['high_risk_prob']*100:.4f}%")
    print(f"{'='*60}\n")
    return result

if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    evaluate_probability(asof)