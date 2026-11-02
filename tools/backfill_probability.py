# -*- coding: utf-8 -*-
"""tools/backfill_probability.py - 用 v6 透明化惩罚逻辑重算历史概率

用法：
  # 1) 默认 dry-run，只看对比，不写库
  python tools/backfill_probability.py --days 30

  # 2) 写入 probability_engine（Brier 展示用）
  python tools/backfill_probability.py --days 30 --apply

  # 3) 同时更新 predictions_log 的 p_r4_r5（让 Brier 校准口径统一）
  python tools/backfill_probability.py --days 30 --apply --apply-log

v6 公式（与 engines_v3/probability_engine.py 完全一致）：
  penalty_factor = 1.0 + 0.15 * stress_count + 0.2 (若 frag >= 65)
  cut_ratio      = min(0.1 * (penalty_factor - 1.0), 0.15)
"""
import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DB_PATH = str(BASE_DIR / 'data' / 'macro.db')
PRIORS = {'R0': 0.55, 'R1': 0.10, 'R2': 0.08, 'R3': 0.12, 'R4': 0.10, 'R5': 0.05}

_HAS_ENGINE = False
try:
    from engines_v3.probability_engine import (
        compute_likelihoods as _engine_cl,
        compute_posteriors as _engine_cp,
    )
    _HAS_ENGINE = True
except Exception as e:
    print(f"⚠️ 无法导入 engines_v3.probability_engine，将使用内置副本逻辑：{e}")


# ============ 核心逻辑（与 v6 完全一致） ============

def compute_likelihoods(z_scores):
    if _HAS_ENGINE:
        return _engine_cl(z_scores)
    inf = z_scores.get('INF', 0)
    mon = z_scores.get('MON', 0)
    fis = z_scores.get('FIS', 0)
    liq = z_scores.get('LIQ', 0)
    risk = z_scores.get('RISK', 0)
    likelihoods = {
        'R0': np.exp(-0.15 * (inf**2 + mon**2 + fis**2 + liq**2 + risk**2)),
        'R1': np.exp(-0.25 * ((inf - 2)**2 + (mon - 1.5)**2 + risk**2)),
        'R2': np.exp(-0.25 * ((inf - 2)**2 + (fis - 2)**2 + (liq - 1)**2)),
        'R3': np.exp(-0.25 * ((mon - 2)**2 + (risk - 2)**2 + (inf - 0.5)**2)),
        'R4': np.exp(-0.25 * ((inf + 1.5)**2 + (liq + 2)**2 + (risk - 2.5)**2)),
        'R5': np.exp(-0.25 * ((risk - 3)**2 + (liq - 2.5)**2 + (mon + 0.5)**2)),
    }
    return {r: max(v, 1e-8) for r, v in likelihoods.items()}


def compute_posteriors(likelihoods):
    if _HAS_ENGINE:
        return _engine_cp(likelihoods)
    total = 0.0
    posteriors = {}
    for regime in PRIORS:
        p = PRIORS[regime] * likelihoods.get(regime, 0)
        posteriors[regime] = p
        total += p
    return {r: p / total for r, p in posteriors.items()} if total > 0 else {r: 0 for r in PRIORS}


def apply_micro_penalty(base_posteriors, triggered_count, frag_score):
    """
    v6 透明化惩罚 —— 与 engines_v3/probability_engine.py 完全一致。
    验证点：stress=3, frag=77.2 -> penalty=1.65, cut_ratio=0.065 (线上日志 x1.65 / 6%)
    """
    penalty_factor = 1.0
    if triggered_count and triggered_count >= 2:
        penalty_factor += 0.15 * triggered_count   # 3层 -> +0.45
    if frag_score and frag_score >= 65:
        penalty_factor += 0.2                       # -> +0.2

    if penalty_factor <= 1.0:
        return base_posteriors, 1.0, 0.0

    adjusted = base_posteriors.copy()
    cut_ratio = min(0.1 * (penalty_factor - 1.0), 0.15)  # 1.65 -> 0.065
    transferred = 0.0
    for r in ['R0', 'R1']:
        if adjusted.get(r, 0) > 0:
            cut = adjusted[r] * cut_ratio
            adjusted[r] -= cut
            transferred += cut

    if transferred > 0:
        adjusted['R4'] = adjusted.get('R4', 0) + transferred * 0.6
        adjusted['R5'] = adjusted.get('R5', 0) + transferred * 0.4

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: v / total for k, v in adjusted.items()}
    return adjusted, penalty_factor, cut_ratio


# ============ 数据读写 ============

def backup_db(db_path):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = f"{db_path}.bak_{ts}"
    shutil.copy2(db_path, bak)
    return bak


def list_dates(conn, days):
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = conn.execute(
        "SELECT DISTINCT asof_date FROM engine_latents "
        "WHERE asof_date >= ? ORDER BY asof_date",
        (cutoff,)
    ).fetchall()
    return [r[0] for r in rows]


def load_z_scores(conn, asof):
    try:
        df = pd.read_sql_query(
            "SELECT engine_id, z_score FROM engine_latents WHERE asof_date=?",
            conn, params=(asof,)
        )
    except Exception:
        return None
    if df.empty:
        return None
    return dict(zip(df['engine_id'], df['z_score']))


def load_stress_count(conn, asof):
    try:
        row = conn.execute(
            "SELECT triggered_count FROM stress_overlay_v2 WHERE asof_date=?",
            (asof,)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def load_frag_score(conn, asof):
    try:
        row = conn.execute(
            "SELECT fragility_score FROM fragility_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return 0.0


def load_old_prob(conn, asof):
    try:
        row = conn.execute(
            "SELECT p_r4, p_r5, high_risk_prob FROM probability_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if row:
            return {
                'p_r4': float(row[0] or 0),
                'p_r5': float(row[1] or 0),
                'high_risk_prob': float(row[2] or 0),
            }
    except Exception:
        pass
    return None


def write_probability(conn, asof, posteriors, p_final):
    conn.execute(
        "INSERT OR REPLACE INTO probability_engine "
        "(asof_date, p_r0, p_r1, p_r2, p_r3, p_r4, p_r5, high_risk_prob, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            asof,
            posteriors.get('R0', 0), posteriors.get('R1', 0), posteriors.get('R2', 0),
            posteriors.get('R3', 0), posteriors.get('R4', 0), posteriors.get('R5', 0),
            p_final,
            json.dumps({'asof': asof, 'high_risk_prob': p_final, 'backfilled': True}),
        )
    )


def update_predictions_log(conn, asof, p_new):
    try:
        row = conn.execute(
            "SELECT details_json FROM predictions_log WHERE forecast_date=?",
            (asof,)
        ).fetchone()
        if not row:
            return False
        details = {}
        if row[0]:
            try:
                details = json.loads(row[0])
            except Exception:
                details = {}
        details['p_r4_r5'] = p_new
        details['p_r4_r5_backfilled'] = True
        conn.execute(
            "UPDATE predictions_log SET p_r4_r5=?, details_json=? WHERE forecast_date=?",
            (p_new, json.dumps(details, ensure_ascii=False), asof)
        )
        return True
    except Exception as e:
        print(f"    ⚠️ 更新 predictions_log 失败 {asof}: {e}")
        return False


# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(description='用 v6 逻辑重算历史概率')
    parser.add_argument('--days', type=int, default=30, help='重算最近 N 天，默认 30')
    parser.add_argument('--apply', action='store_true', help='写入 probability_engine')
    parser.add_argument('--apply-log', action='store_true',
                        help='同时更新 predictions_log 的 p_r4_r5（需配合 --apply）')
    args = parser.parse_args()

    if args.apply_log and not args.apply:
        print("❌ --apply-log 必须配合 --apply 使用")
        sys.exit(1)

    if not Path(DB_PATH).exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*74}")
    print(f"  Backfill Probability ({mode}) - 最近 {args.days} 天")
    print(f"  DB: {DB_PATH}")
    print(f"  v6 公式: penalty += 0.15*stress + 0.2(if frag>=65); cut = min(0.1*(penalty-1), 0.15)")
    print(f"{'='*74}\n")

    conn = sqlite3.connect(DB_PATH, timeout=15)
    dates = list_dates(conn, args.days)
    if not dates:
        print("⚠️ 最近 N 天没有 engine_latents 数据，退出。")
        conn.close()
        return

    print(f"发现 {len(dates)} 个候选日期: {dates[0]} ~ {dates[-1]}\n")

    rows = []
    skipped = []
    for asof in dates:
        z = load_z_scores(conn, asof)
        if not z:
            skipped.append((asof, 'no engine_latents'))
            continue

        stress_count = load_stress_count(conn, asof)
        frag_score = load_frag_score(conn, asof)

        likelihoods = compute_likelihoods(z)
        base_post = compute_posteriors(likelihoods)
        p_base = round(base_post['R4'] + base_post['R5'], 4)

        final_post, penalty, cut_ratio = apply_micro_penalty(base_post, stress_count, frag_score)
        p_final = round(final_post['R4'] + final_post['R5'], 4)

        old = load_old_prob(conn, asof)
        old_p = old['high_risk_prob'] if old else None

        rows.append({
            'asof': asof,
            'old_p': old_p,
            'new_p': p_final,
            'p_base': p_base,
            'penalty': penalty,
            'cut': cut_ratio,
            'stress': stress_count,
            'frag': frag_score,
            'posteriors': final_post,
        })

    print(f"{'日期':<12} {'旧P':>8} {'新P':>8} {'基准P':>8} {'惩罚':>6} {'砍%':>6} {'S':>3} {'Frag':>6} {'变化':>9}")
    print("-" * 82)
    for r in rows:
        old_s = f"{r['old_p']*100:.2f}%" if r['old_p'] is not None else "N/A"
        delta = ""
        if r['old_p'] is not None:
            d = (r['new_p'] - r['old_p']) * 100
            delta = f"{d:+.2f}pp"
        print(f"{r['asof']:<12} {old_s:>8} {r['new_p']*100:>7.2f}% "
              f"{r['p_base']*100:>7.2f}% {r['penalty']:>6.2f} "
              f"{r['cut']*100:>5.1f}% {r['stress']:>3} {r['frag']:>6.1f} {delta:>9}")

    if skipped:
        print("\n⚠️ 跳过日期：")
        for asof, reason in skipped:
            print(f"  - {asof}: {reason}")

    # 自检：和线上 11-02 的 9.33% 对比
    self_check = [r for r in rows if r['asof'] == '2026-11-02']
    if self_check:
        r = self_check[0]
        if r['old_p'] is not None:
            diff = abs(r['new_p'] - r['old_p']) * 100
            print(f"\n🔎 自检 2026-11-02: 新P={r['new_p']*100:.2f}% vs 线上={r['old_p']*100:.2f}% "
                  f"(偏差 {diff:.2f}pp)")
            if diff > 2.0:
                print(f"   ⚠️ 偏差 > 2pp，回填脚本可能仍与线上 v6 不一致，请勿 --apply")
            else:
                print(f"   ✅ 偏差在 2pp 内，口径一致")

    valid = [r for r in rows if r['old_p'] is not None]
    if valid:
        avg_delta = np.mean([(r['new_p'] - r['old_p']) * 100 for r in valid])
        max_abs = max(abs((r['new_p'] - r['old_p']) * 100) for r in valid)
        print(f"\n📊 汇总（{len(valid)} 天可比）：平均变化 {avg_delta:+.2f}pp，最大绝对变化 {max_abs:.2f}pp")

    if not args.apply:
        print(f"\n🟡 DRY-RUN 模式：未写入数据库。")
        print(f"   如需写入 probability_engine，加 --apply")
        print(f"   如需同时统一 predictions_log 口径，加 --apply --apply-log")
        conn.close()
        return

    bak = backup_db(DB_PATH)
    print(f"\n💾 已备份数据库: {bak}")

    written = 0
    log_updated = 0
    try:
        for r in rows:
            write_probability(conn, r['asof'], r['posteriors'], r['new_p'])
            written += 1
            if args.apply_log:
                if update_predictions_log(conn, r['asof'], r['new_p']):
                    log_updated += 1
        conn.commit()
        print(f"✅ 已写入 probability_engine: {written} 条")
        if args.apply_log:
            print(f"✅ 已更新 predictions_log: {log_updated} 条")
        else:
            print(f"ℹ️ predictions_log 未改动（未加 --apply-log），Brier 校准仍读旧 p_r4_r5")
    except Exception as e:
        conn.rollback()
        print(f"❌ 写库失败，已回滚: {e}")
    finally:
        conn.close()

    print(f"\n{'='*74}\n  完成\n{'='*74}\n")


if __name__ == '__main__':
    main()