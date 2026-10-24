"""engines_v3/calibration_tracker.py - VS4: Probability Calibration
每天记录预测，30/60/90天后回填实际结果，计算 Brier Score
"""
import sqlite3
import json
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'


def _init_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prediction_log (
            asof_date TEXT PRIMARY KEY,
            regime TEXT,
            p_r4 REAL,
            p_r5 REAL,
            p_high_risk REAL,
            fragility_score REAL,
            fragility_level TEXT,
            shock_primary TEXT,
            stress_overall TEXT,
            risk_gate TEXT,
            actual_30d_return REAL,
            actual_60d_return REAL,
            actual_90d_return REAL,
            brier_30d REAL,
            brier_60d REAL,
            brier_90d REAL,
            evaluated_at TEXT
        )
    """)
    conn.commit()


def _read_current_state(conn, asof):
    """读取当日各模块的最新状态"""
    state = {'asof': asof}

    # Regime
    try:
        r = conn.execute(
            "SELECT regime_label FROM gms_regimes WHERE asof_date=?",
            (asof,)
        ).fetchone()
        state['regime'] = r[0] if r else None
    except Exception:
        state['regime'] = None

    # Probability
    try:
        r = conn.execute(
            "SELECT p_r4, p_r5, high_risk_prob FROM probability_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if r:
            state['p_r4'], state['p_r5'], state['p_high_risk'] = r
        else:
            state['p_r4'] = state['p_r5'] = state['p_high_risk'] = None
    except Exception:
        state['p_r4'] = state['p_r5'] = state['p_high_risk'] = None

    # Fragility
    try:
        r = conn.execute(
            "SELECT fragility_score, level FROM fragility_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        if r:
            state['fragility_score'], state['fragility_level'] = r
        else:
            state['fragility_score'] = state['fragility_level'] = None
    except Exception:
        state['fragility_score'] = state['fragility_level'] = None

    # Shock
    try:
        r = conn.execute(
            "SELECT primary_shock FROM shock_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        state['shock_primary'] = r[0] if r else None
    except Exception:
        state['shock_primary'] = None

    # Stress Overlay
    try:
        r = conn.execute(
            "SELECT overall FROM stress_overlay_v2 WHERE asof_date=?",
            (asof,)
        ).fetchone()
        state['stress_overall'] = r[0] if r else None
    except Exception:
        state['stress_overall'] = None

    return state


def _read_risk_gate(conn, asof):
    """从 stress + fragility 推算 Risk Gate"""
    try:
        frag = conn.execute(
            "SELECT fragility_score FROM fragility_engine WHERE asof_date=?",
            (asof,)
        ).fetchone()
        stress = conn.execute(
            "SELECT overall FROM stress_overlay_v2 WHERE asof_date=?",
            (asof,)
        ).fetchone()

        frag_score = float(frag[0]) if frag and frag[0] else 50
        stress_str = stress[0] if stress else ''

        if 'SYSTEMIC' in stress_str:
            return 'BLACK'
        elif frag_score >= 80 or ('FUNDING' in stress_str and 'CREDIT' in stress_str):
            return 'RED'
        elif frag_score >= 65 or stress_str.count('+') >= 1:
            return 'ORANGE'
        elif frag_score >= 50:
            return 'YELLOW'
        else:
            return 'GREEN'
    except Exception:
        return None


def log_today(asof: str = None) -> dict:
    """记录今日预测"""
    if asof is None:
        asof = datetime.now().strftime('%Y-%m-%d')

    conn = sqlite3.connect(DB_PATH)
    try:
        _init_table(conn)
        state = _read_current_state(conn, asof)
        gate = _read_risk_gate(conn, asof)
        state['risk_gate'] = gate

        conn.execute("""
            INSERT OR REPLACE INTO prediction_log
            (asof_date, regime, p_r4, p_r5, p_high_risk, fragility_score,
             fragility_level, shock_primary, stress_overall, risk_gate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asof,
            state['regime'],
            state['p_r4'], state['p_r5'], state['p_high_risk'],
            state['fragility_score'], state['fragility_level'],
            state['shock_primary'], state['stress_overall'], gate
        ))
        conn.commit()

        print(f"\n{'='*60}")
        print(f"  Calibration Log - {asof}")
        print(f"{'='*60}")
        print(f"  Regime:        {state['regime']}")
        print(f"  P(R4+R5):      {state['p_high_risk']*100:.2f}%" if state['p_high_risk'] else "  P(R4+R5):      N/A")
        print(f"  Fragility:     {state['fragility_level']} ({state['fragility_score']})" if state['fragility_score'] else "  Fragility:     N/A")
        print(f"  Primary Shock: {state['shock_primary']}")
        print(f"  Stress:        {state['stress_overall']}")
        print(f"  Risk Gate:     {gate}")
        print(f"{'='*60}\n")

        return state
    finally:
        conn.close()


def evaluate_outcomes() -> dict:
    """评估 30/60/90 天前的预测，回填 SP500 实际收益 + Brier Score"""
    conn = sqlite3.connect(DB_PATH)
    results = {'evaluated': 0, 'brier_scores': []}

    try:
        _init_table(conn)

        # 找 30 天前需要评估的
        cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        rows = conn.execute("""
            SELECT asof_date, p_high_risk FROM prediction_log
            WHERE actual_30d_return IS NULL AND asof_date <= ?
        """, (cutoff,)).fetchall()

        print(f"\n{'='*60}")
        print(f"  Calibration Evaluation")
        print(f"{'='*60}")
        print(f"  待评估预测（30天前）: {len(rows)} 条\n")

        for asof, p_hr in rows:
            # 获取 SP500 起点和 30 天后
            sp0 = conn.execute("""
                SELECT value FROM observations WHERE series_id='SP500'
                AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1
            """, (asof,)).fetchone()

            t30 = (datetime.strptime(asof, '%Y-%m-%d') + timedelta(days=30)).strftime('%Y-%m-%d')
            sp30 = conn.execute("""
                SELECT value FROM observations WHERE series_id='SP500'
                AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1
            """, (t30,)).fetchone()

            if sp0 and sp30 and sp0[0] > 0:
                ret_30d = (sp30[0] - sp0[0]) / sp0[0]

                # Brier Score: 定义"高风险事件"为 30 天收益 < -5%
                actual_event = 1 if ret_30d < -0.05 else 0
                brier = (p_hr - actual_event) ** 2 if p_hr is not None else None

                conn.execute("""
                    UPDATE prediction_log
                    SET actual_30d_return = ?, brier_30d = ?, evaluated_at = ?
                    WHERE asof_date = ?
                """, (ret_30d, brier, datetime.now().isoformat(), asof))

                results['evaluated'] += 1
                if brier is not None:
                    results['brier_scores'].append(brier)

                print(f"  {asof}: P(high)={p_hr*100:.1f}% | 实际30D={ret_30d*100:+.2f}% | Brier={brier:.4f}" if brier is not None else f"  {asof}: 无预测数据")

        conn.commit()

        # 汇总
        if results['brier_scores']:
            avg_brier = sum(results['brier_scores']) / len(results['brier_scores'])
            print(f"\n  {'='*58}")
            print(f"  平均 Brier Score: {avg_brier:.4f}")
            print(f"  判定标准:")
            print(f"    0.00-0.10 = 优秀（预测很准）")
            print(f"    0.10-0.20 = 良好")
            print(f"    0.20-0.25 = 一般（接近随机）")
            print(f"    > 0.25    = 差（比随机更糟）")
            print(f"  {'='*58}\n")
            results['avg_brier'] = avg_brier
        else:
            print(f"\n  ℹ️ 还没有可评估的预测（需要至少 30 天历史）")
            print(f"  建议：每天运行 log_today() 累积数据\n")

        return results
    finally:
        conn.close()


def show_history() -> None:
    """显示预测历史"""
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("""
            SELECT asof_date, regime, p_high_risk, fragility_level, risk_gate,
                   actual_30d_return, brier_30d
            FROM prediction_log ORDER BY asof_date DESC LIMIT 30
        """).fetchall()

        print(f"\n{'='*100}")
        print(f"  Prediction History (最近30条)")
        print(f"{'='*100}")
        print(f"{'日期':12s} {'Regime':8s} {'P(R4+R5)':>10s} {'Fragility':>12s} {'Gate':>8s} {'实际30D':>10s} {'Brier':>8s}")
        print(f"{'-'*100}")

        for row in rows:
            asof, regime, p_hr, frag, gate, ret, brier = row
            p_str = f"{p_hr*100:.1f}%" if p_hr else "N/A"
            ret_str = f"{ret*100:+.2f}%" if ret else "未评估"
            brier_str = f"{brier:.4f}" if brier else "-"
            print(f"{asof:12s} {str(regime or 'N/A'):8s} {p_str:>10s} {str(frag or 'N/A'):>12s} {str(gate or 'N/A'):>8s} {ret_str:>10s} {brier_str:>8s}")

        print(f"{'='*100}\n")
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'log':
            log_today()
        elif cmd == 'evaluate':
            evaluate_outcomes()
        elif cmd == 'history':
            show_history()
        else:
            print(f"未知命令: {cmd}")
            print("用法: python calibration_tracker.py [log|evaluate|history]")
    else:
        # 默认：记录 + 评估
        log_today()
        evaluate_outcomes()
        show_history()