# -*- coding: utf-8 -*-
"""tools/fix_prediction_log.py - 用 probability_engine 新值回填 prediction_log

用法：
  # 1) dry-run，只看对比
  python tools/fix_prediction_log.py

  # 2) 执行 UPDATE（自动备份）
  python tools/fix_prediction_log.py --apply
"""
import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = str(BASE_DIR / 'data' / 'macro.db')
CUTOFF = '2026-10-03'  # 只更新这一天及之后；9-12 已评估样本不动


def list_diff(conn):
    sql = """
        SELECT pl.asof_date, pl.p_r4, pl.p_r5, pl.p_high_risk,
               pe.p_r4, pe.p_r5, pe.high_risk_prob
        FROM prediction_log pl
        JOIN probability_engine pe ON pl.asof_date = pe.asof_date
        WHERE pl.asof_date >= ?
        ORDER BY pl.asof_date
    """
    return conn.execute(sql, (CUTOFF,)).fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='执行 UPDATE')
    args = parser.parse_args()

    if not Path(DB_PATH).exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        sys.exit(1)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*70}")
    print(f"  Fix prediction_log ({mode})")
    print(f"  DB: {DB_PATH}")
    print(f"  范围: asof_date >= {CUTOFF}（9-12 已评估样本不动）")
    print(f"{'='*70}\n")

    conn = sqlite3.connect(DB_PATH, timeout=15)
    rows = list_diff(conn)

    if not rows:
        print("⚠️ 没有可更新的记录（prediction_log 与 probability_engine 无交集）")
        conn.close()
        return

    print(f"{'日期':<12} {'旧p_high_risk':>14} {'新p_high_risk':>14} {'变化':>10}")
    print("-" * 58)
    for r in rows:
        asof, old_r4, old_r5, old_p, new_r4, new_r5, new_p = r
        delta = (new_p - old_p) * 100
        print(f"{asof:<12} {old_p*100:>13.2f}% {new_p*100:>13.2f}% {delta:>+9.2f}pp")

    print(f"\n共 {len(rows)} 条将更新")

    # 检查 9-12 是否在范围内（应该不在）
    s912 = conn.execute(
        "SELECT asof_date, p_high_risk, brier_30d FROM prediction_log WHERE asof_date='2026-09-12'"
    ).fetchone()
    if s912:
        print(f"\n🔒 保护样本 2026-09-12: p_high_risk={s912[1]*100:.2f}%, brier_30d={s912[2]}（不动）")

    if not args.apply:
        print(f"\n🟡 DRY-RUN：未写库。加 --apply 执行更新。")
        conn.close()
        return

    # 备份
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = f"{DB_PATH}.bak_predlog_{ts}"
    shutil.copy2(DB_PATH, bak)
    print(f"\n💾 已备份: {bak}")

    # UPDATE
    update_sql = """
        UPDATE prediction_log
        SET p_r4 = (SELECT pe.p_r4 FROM probability_engine pe WHERE pe.asof_date = prediction_log.asof_date),
            p_r5 = (SELECT pe.p_r5 FROM probability_engine pe WHERE pe.asof_date = prediction_log.asof_date),
            p_high_risk = (SELECT pe.high_risk_prob FROM probability_engine pe WHERE pe.asof_date = prediction_log.asof_date)
        WHERE asof_date >= ?
          AND EXISTS (SELECT 1 FROM probability_engine pe WHERE pe.asof_date = prediction_log.asof_date)
    """
    try:
        cur = conn.cursor()
        cur.execute(update_sql, (CUTOFF,))
        updated = cur.rowcount
        conn.commit()
        print(f"✅ 已更新 {updated} 条 prediction_log 记录")
    except Exception as e:
        conn.rollback()
        print(f"❌ UPDATE 失败，已回滚: {e}")
        conn.close()
        return

    # 验证
    print(f"\n{'='*70}\n  验证（最近 20 条）\n{'='*70}")
    verify = conn.execute("""
        SELECT asof_date, p_high_risk, fragility_level, risk_gate,
               actual_30d_return, brier_30d
        FROM prediction_log ORDER BY asof_date DESC LIMIT 20
    """).fetchall()
    for r in verify:
        asof, p, frag, gate, actual, brier = r
        actual_s = f"{actual:+.4f}" if actual is not None else "未评估"
        brier_s = f"{brier:.6f}" if brier is not None else "-"
        print(f"{asof}  p={p*100:>6.2f}%  {frag:<20} {gate:<7} "
              f"actual30d={actual_s:>12}  brier={brier_s:>10}")

    conn.close()
    print(f"\n{'='*70}\n  完成\n{'='*70}\n")


if __name__ == '__main__':
    main()