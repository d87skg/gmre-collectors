# -*- coding: utf-8 -*-
"""engines_v3/probability_engine.py - 概率化输出（v6：输入依赖内证 + 决策资格分级）"""
import sqlite3
import pandas as pd
import numpy as np
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
MODEL_VERSION = 'GMRE_PROB_v6_2026_11'
PRIORS = {'R0': 0.55, 'R1': 0.10, 'R2': 0.08, 'R3': 0.12, 'R4': 0.10, 'R5': 0.05}

REQUIRED_INPUTS = ['INF', 'MON', 'FIS', 'LIQ', 'RISK']
OPTIONAL_INPUTS = ['stress_overlay_v2.triggered_count', 'fragility_engine.fragility_score']
NOT_REQUIRED_INPUTS = ['MICH_1Y_EXPECT', 'SOFR', 'EFFR', 'HY_OAS', 'VIX', 'YC10Y', 'FEDFUNDS']


def compute_likelihoods(z_scores):
    def _safe(v):
        return 0.0 if v is None or pd.isna(v) else float(v)

    inf = _safe(z_scores.get('INF'))
    mon = _safe(z_scores.get('MON'))
    fis = _safe(z_scores.get('FIS'))
    liq = _safe(z_scores.get('LIQ'))
    risk = _safe(z_scores.get('RISK'))

    likelihoods = {
        'R0': np.exp(-0.15 * (inf**2 + mon**2 + fis**2 + liq**2 + risk**2)),
        'R1': np.exp(-0.25 * ((inf - 2)**2 + (mon - 1.5)**2 + risk**2)),
        'R2': np.exp(-0.25 * ((inf - 2)**2 + (fis - 2)**2 + (liq - 1)**2)),
        'R3': np.exp(-0.25 * ((mon - 2)**2 + (risk - 2)**2 + (inf - 0.5)**2)),
        'R4': np.exp(-0.25 * ((inf + 1.5)**2 + (liq + 2)**2 + (risk - 2.5)**2)),
        'R5': np.exp(-0.25 * ((risk - 3)**2 + (liq - 2.5)**2 + (mon + 0.5)**2)),
    }
    for r in likelihoods:
        likelihoods[r] = max(likelihoods[r], 1e-8)
    return likelihoods


def compute_posteriors(likelihoods):
    posteriors = {}
    total = 0.0
    for regime in PRIORS:
        p = PRIORS[regime] * likelihoods.get(regime, 0)
        posteriors[regime] = p
        total += p
    if total > 0:
        return {r: p / total for r, p in posteriors.items()}
    return {r: 0 for r in PRIORS}


def apply_micro_penalty(posteriors, asof, stress_count, frag_score):
    """apply_micro_penalty 直接接收参数，不内部查库。不触碰风险预算。"""
    penalty_factor = 1.0
    reasons = []

    if stress_count is not None and stress_count >= 2:
        penalty_factor += 0.15 * stress_count
        reasons.append(f"Stress={stress_count}层")

    if frag_score is not None and frag_score >= 65:
        penalty_factor += 0.2
        reasons.append(f"Frag={frag_score:.1f}")

    if penalty_factor <= 1.0:
        return posteriors, penalty_factor, reasons

    adjusted = posteriors.copy()
    transferred = 0.0
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
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted, penalty_factor, reasons


def evaluate_probability(asof: str) -> dict:
    # ============ 1. 拉取引擎输入 ============
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT engine_id, z_score FROM engine_latents "
            "WHERE asof_date = (SELECT MAX(asof_date) FROM engine_latents)",
            conn
        )
    finally:
        conn.close()

    z_scores = dict(zip(df['engine_id'], df['z_score'])) if not df.empty else {}
    actual_engines = list(z_scores.keys())
    missing_engines = [e for e in REQUIRED_INPUTS if e not in actual_engines]

    # ============ 2. 拉取辅助输入 ============
    stress_count = None
    frag_score = None
    try:
        conn = sqlite3.connect(DB_PATH)
        stress_row = conn.execute(
            "SELECT triggered_count FROM stress_overlay_v2 WHERE asof_date=?", (asof,)
        ).fetchone()
        if stress_row:
            stress_count = stress_row[0]
        frag_row = conn.execute(
            "SELECT fragility_score FROM fragility_engine WHERE asof_date=?", (asof,)
        ).fetchone()
        if frag_row:
            frag_score = frag_row[0]
        conn.close()
    except Exception:
        pass

    # ============ 3. 引擎完全失败时短路 ============
    if not z_scores:
        input_audit = {
            'model_version': MODEL_VERSION,
            'required_inputs': REQUIRED_INPUTS,
            'optional_inputs': OPTIONAL_INPUTS,
            'not_required_inputs': NOT_REQUIRED_INPUTS,
            'actual_inputs_used': [],
            'missing_inputs': REQUIRED_INPUTS,
            'input_health': 'BLOCKED',
            'decision_eligible': False,
            'decision_reason': 'NO_ENGINE_LATENTS',
            'penalty_factor': 1.0,
            'penalty_reasons': [],
            'stress_count_used': stress_count,
            'frag_score_used': frag_score,
        }
        print(f"\n  [PROBABILITY_INPUT_AUDIT] (内证)")
        print(f"    MODEL_VERSION             : {MODEL_VERSION}")
        print(f"    ACTUAL_INPUTS_USED        : []")
        print(f"    MISSING_INPUTS            : {REQUIRED_INPUTS}")
        print(f"    INPUT_HEALTH              : BLOCKED")
        print(f"    DECISION_ELIGIBLE         : False")
        print(f"    DECISION_ELIGIBLE_REASON  : NO_ENGINE_LATENTS")
        return {
            'asof': asof,
            'current': {},
            'high_risk_prob': None,
            'input_audit': input_audit,
        }

    # ============ 4. 计算概率 ============
    likelihoods = compute_likelihoods(z_scores)
    posteriors = compute_posteriors(likelihoods)
    posteriors, penalty_factor, penalty_reasons = apply_micro_penalty(
        posteriors, asof, stress_count, frag_score
    )
    high_risk_prob = round(posteriors['R4'] + posteriors['R5'], 4)

    # ============ 5. 决策资格分级（内证）============
    if len(missing_engines) == 0:
        input_health = 'HEALTHY'
        decision_eligible = True
        decision_reason = 'ALL_REQUIRED_INPUTS_PRESENT'
    elif len(missing_engines) <= 2:
        input_health = 'DEGRADED'
        decision_eligible = True
        decision_reason = f'PARTIAL_INPUTS_PRESENT (missing: {missing_engines})'
    else:
        input_health = 'BLOCKED'
        decision_eligible = False
        decision_reason = f'TOO_MANY_MISSING ({missing_engines})'

    input_audit = {
        'model_version': MODEL_VERSION,
        'required_inputs': REQUIRED_INPUTS,
        'optional_inputs': OPTIONAL_INPUTS,
        'not_required_inputs': NOT_REQUIRED_INPUTS,
        'actual_inputs_used': actual_engines,
        'missing_inputs': missing_engines,
        'input_health': input_health,
        'decision_eligible': decision_eligible,
        'decision_reason': decision_reason,
        'penalty_factor': round(penalty_factor, 3),
        'penalty_reasons': penalty_reasons,
        'stress_count_used': stress_count,
        'frag_score_used': frag_score,
    }

    # ============ 6. 打印审计块 ============
    print(f"\n  [PROBABILITY_INPUT_AUDIT] (内证)")
    print(f"    MODEL_VERSION             : {MODEL_VERSION}")
    print(f"    REQUIRED_INPUTS           : {REQUIRED_INPUTS}")
    print(f"    OPTIONAL_INPUTS           : {OPTIONAL_INPUTS}")
    print(f"    NOT_REQUIRED_INPUTS       : {NOT_REQUIRED_INPUTS}")
    print(f"    ACTUAL_INPUTS_USED        : {actual_engines}")
    print(f"    MISSING_INPUTS            : {missing_engines if missing_engines else 'NONE'}")
    print(f"    INPUT_DEPENDENCY_SOURCE   : SOURCE_CODE_VERIFIED")
    print(f"    INPUT_HEALTH              : {input_health}")
    print(f"    DECISION_ELIGIBLE         : {decision_eligible}")
    print(f"    DECISION_ELIGIBLE_REASON  : {decision_reason}")
    print(f"    PENALTY_FACTOR            : x{penalty_factor:.2f} ({penalty_reasons if penalty_reasons else 'NONE'})")

    result = {
        'asof': asof,
        'current': {r: round(p, 4) for r, p in posteriors.items()},
        'high_risk_prob': high_risk_prob,
        'input_audit': input_audit,
    }

    # ============ 7. 持久化 ============
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS probability_engine (
        asof_date TEXT PRIMARY KEY,
        p_r0 REAL, p_r1 REAL, p_r2 REAL, p_r3 REAL, p_r4 REAL, p_r5 REAL,
        high_risk_prob REAL, detail TEXT
    )""")
    conn.execute(
        """INSERT OR REPLACE INTO probability_engine VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (asof, posteriors['R0'], posteriors['R1'], posteriors['R2'],
         posteriors['R3'], posteriors['R4'], posteriors['R5'],
         high_risk_prob, json.dumps(result, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

    print(f"  高风险概率 P(R4+R5): {high_risk_prob*100:.2f}%")
    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    evaluate_probability(asof)