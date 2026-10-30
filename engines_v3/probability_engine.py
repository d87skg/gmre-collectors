"""engines_v3/probability_engine.py - 概率化输出（贝叶斯平滑 + 微观加压防精神分裂版）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

PRIORS = {
    'R0': 0.55, 'R1': 0.10, 'R2': 0.08, 'R3': 0.12, 'R4': 0.10, 'R5': 0.05,
}


# ============================================================
# 一、贝叶斯似然度计算（保持原逻辑不变）
# ============================================================
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


# ============================================================
# 二、贝叶斯后验更新（保持原逻辑不变）
# ============================================================
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


# ============================================================
# 三、P1 新增：微观风控加压（Penalty）
# ============================================================
def apply_micro_penalty(posteriors: dict, asof: str) -> dict:
    """微观风控加压（Penalty）
    如果 Stress Overlay 被触发（>=2层），或 Fragility 极高（>=65），
    强制压低宏观乐观度（R0/R1），把概率按 6:4 分配给 R4/R5。
    使宏观概率引擎与微观风控信号彻底对齐，消灭"R0 精神分裂"。
    """
    penalty_factor = 1.0  # 初始惩罚系数（>1 代表把概率往 R4/R5 推）
    reasons = []

    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            # 1) 检查 Stress Overlay V2 的触发层数
            stress_row = conn.execute(
                "SELECT triggered_count FROM stress_overlay_v2 WHERE asof_date=?",
                (asof,)
            ).fetchone()
            if stress_row and stress_row[0] is not None and stress_row[0] >= 2:
                penalty_factor += 0.5 * stress_row[0]
                reasons.append(f"Stress触发{stress_row[0]}层")

            # 2) 检查 Fragility 的分数
            frag_row = conn.execute(
                "SELECT fragility_score FROM fragility_engine WHERE asof_date=?",
                (asof,)
            ).fetchone()
            if frag_row and frag_row[0] is not None and frag_row[0] >= 65:
                penalty_factor += 1.0
                reasons.append(f"Fragility={frag_row[0]:.1f}")
        finally:
            conn.close()
    except Exception as e:
        print(f"  ⚠️ 概率惩罚检查异常: {e}")

    # 未触发任何惩罚条件，直接返回原概率
    if penalty_factor <= 1.0:
        print(f"  ℹ️  [微观加压] 未触发（penalty_factor=1.0），保持原始概率")
        return posteriors

    # === 开始实施惩罚：削减 R0/R1，转移给 R4/R5 ===
    adjusted = posteriors.copy()
    transferred = 0.0
    cut_ratio = min(0.2 * (penalty_factor - 1.0), 0.8)  # 单侧最多砍掉80%

    for r in ['R0', 'R1']:
        if adjusted.get(r, 0) > 0:
            cut = adjusted[r] * cut_ratio
            adjusted[r] -= cut
            transferred += cut

    # 转移给 R4/R5（按 6:4 分配）
    if transferred > 0:
        adjusted['R4'] = adjusted.get('R4', 0.0) + transferred * 0.6
        adjusted['R5'] = adjusted.get('R5', 0.0) + transferred * 0.4

    # 重新归一化
    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}

    print(f"  ⚠️ [微观加压] 触发惩罚因子 x{penalty_factor:.1f} "
          f"(原因: {', '.join(reasons) or 'N/A'}, 砍概率比例: {cut_ratio*100:.0f}%)")
    return adjusted


# ============================================================
# 四、主评估入口（保留全部原逻辑 + P1 加压）
# ============================================================
def evaluate_probability(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Probability Engine - {asof}")
    print(f"{'='*60}\n")

    # --- 读取五引擎 Z-score ---
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

    # --- 似然度 ---
    likelihoods = compute_likelihoods(z_scores)
    print("[1/2] 似然度 P(Data|Regime) (采用平滑防下溢)：")
    for r, l in sorted(likelihoods.items()):
        print(f"    {r}: {l:.8e}")

    # --- 后验 ---
    posteriors = compute_posteriors(likelihoods)

    # --- P1：施加微观惩罚 ---
    posteriors = apply_micro_penalty(posteriors, asof)

    # --- 审计表 ---
    print(f"\n  🔍 [审计中间变量] 先验 / 似然 / 后验 (已叠加微观惩罚)")
    print(f"    {'State':<4} | {'Prior':<8} | {'Likelihood':<14} | {'Posterior':<10}")
    print(f"    {'-'*4} | {'-'*8} | {'-'*14} | {'-'*10}")
    for r in sorted(PRIORS.keys()):
        prior = PRIORS[r]
        lik = likelihoods.get(r, 0.0)
        post = posteriors.get(r, 0.0) * 100
        print(f"    {r:<4} | {prior:<8.3f} | {lik:<14.8e} | {post:>8.4f}%")

    # --- 后验打印 ---
    print(f"\n[2/2] 后验概率：")
    for r in sorted(posteriors.keys()):
        bar = '█' * int(posteriors[r] * 50)
        print(f"    P({r}) = {posteriors[r]*100:7.4f}% {bar}")

    # --- 未来 1 周 / 1 月 外推（基于已加压的 posteriors，保证一致性）---
    future_1w = {}
    future_1m = {}
    for r, p in posteriors.items():
        future_1w[r] = p * 0.95 + PRIORS[r] * 0.05
        future_1m[r] = p * 0.85 + PRIORS[r] * 0.15

    total_1w = sum(future_1w.values())
    total_1m = sum(future_1m.values())
    future_1w = {r: p / total_1w for r, p in future_1w.items()}
    future_1m = {r: p / total_1m for r, p in future_1m.items()}

    # --- 组装结果 ---
    result = {
        'asof': asof,
        'current': {r: round(p, 4) for r, p in posteriors.items()},
        'future_1w': {r: round(p, 4) for r, p in future_1w.items()},
        'future_1m': {r: round(p, 4) for r, p in future_1m.items()},
        'high_risk_prob': round(posteriors['R4'] + posteriors['R5'], 4)
    }

    # --- 落表 ---
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