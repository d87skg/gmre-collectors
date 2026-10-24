"""engines_v3/live_scorecard.py - 每日信号记录与校准追踪"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'


def record_scorecard(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  Live Scorecard - {asof}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(DB_PATH)
    try:
        # 建表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS live_scorecard (
                asof_date TEXT PRIMARY KEY,
                regime TEXT,
                p_r4 REAL, p_r5 REAL, p_high_risk REAL,
                defenses_triggered INTEGER,
                hedge_pct REAL,
                positioning_stress REAL,
                breadth_pct REAL,
                contagion_status TEXT,
                snapshot TEXT,
                future_1w_spx REAL,
                future_1m_spx REAL,
                future_1w_btc REAL,
                future_1m_btc REAL
            )
        """)

        # 读取各模块最新结果
        def _latest(table, col):
            try:
                r = conn.execute(
                    f"SELECT {col} FROM {table} ORDER BY asof_date DESC LIMIT 1"
                ).fetchone()
                return r[0] if r else None
            except Exception:
                return None

        regime = _latest('gms_regimes', 'regime_label')
        p_r4 = _latest('probability_engine', 'p_r4')
        p_r5 = _latest('probability_engine', 'p_r5')
        p_high = _latest('probability_engine', 'high_risk_prob')
        defenses = _latest('defense_v3', 'triggered_count')
        hedge_pct = _latest('hedge_actions', 'size_pct')
        positioning = _latest('positioning_engine', 'stress_score')
        breadth = _latest('velocity_engine', 'breadth_pct')
        contagion = _latest('contagion_engine', 'status')

        # 完整的 snapshot
        snapshot = {
            'regime': regime,
            'p_r4': p_r4,
            'p_r5': p_r5,
            'high_risk_prob': p_high,
            'defenses_triggered': defenses,
            'positioning_stress': positioning,
            'breadth_pct': breadth,
            'contagion_status': contagion
        }

        # 写入
        conn.execute("""
            INSERT OR REPLACE INTO live_scorecard
            (asof_date, regime, p_r4, p_r5, p_high_risk, defenses_triggered,
             hedge_pct, positioning_stress, breadth_pct, contagion_status, snapshot)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (asof, regime, p_r4, p_r5, p_high, defenses,
              hedge_pct, positioning, breadth, contagion, json.dumps(snapshot)))
        conn.commit()

        # 读取最近10天历史
        df = pd.read_sql_query("""
            SELECT asof_date, regime, p_high_risk, defenses_triggered,
                   positioning_stress, breadth_pct, contagion_status
            FROM live_scorecard
            ORDER BY asof_date DESC LIMIT 10
        """, conn)
    finally:
        conn.close()

    print(f"  ✅ 已记录 {asof} 的信号快照")
    print(f"\n  最近10天记录：")
    print(df.to_string(index=False))
    print(f"\n  ⏳ 未来收益（1W/1M）将在 1周/1月后自动回填（待实现）")
    print(f"{'='*60}\n")

    return snapshot


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    record_scorecard(asof)