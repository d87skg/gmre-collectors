"""engines_v3/engine_inf_expect.py - 通胀预期引擎（审计新增）"""
import requests
import sqlite3
import io
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
PROXIES = None


# FRED序列
INF_EXPECT_SERIES = {
    'MICH':     'MICH_1Y_EXPECT',    # 密歇根1年通胀预期
    'MICH5Y':   'MICH_5Y_EXPECT',    # 密歇根5年通胀预期
    'UMCSENT':  'CONSUMER_SENTIMENT', # 消费者信心
}


def fetch_series():
    """拉取通胀预期序列"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0

    for fred_id, local_id in INF_EXPECT_SERIES.items():
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
            r = requests.get(url, timeout=30, proxies=PROXIES)
            if r.status_code != 200:
                print(f"  ⚠️ {fred_id}: HTTP {r.status_code}")
                continue

            df = pd.read_csv(io.StringIO(r.text))
            df.columns = ['date', 'value']
            df = df[df['value'] != '.']

            for _, row in df.iterrows():
                try:
                    c.execute(
                        """INSERT OR REPLACE INTO observations
                        (series_id, timestamp, value, source, retrieved_at)
                        VALUES (?, ?, ?, ?, datetime('now'))""",
                        (local_id, str(row['date']), float(row['value']), 'fred_csv')
                    )
                    count += 1
                except Exception:
                    pass
            print(f"  ✅ {fred_id} -> {local_id}: {len(df)}条")
        except Exception as e:
            print(f"  ❌ {fred_id}: {str(e)[:60]}")

    conn.commit()
    conn.close()
    return count


def compute_engine(asof: str) -> dict:
    """评估通胀预期压力"""
    print(f"\n{'='*60}")
    print(f"  INF_EXPECT Engine - {asof}")
    print(f"{'='*60}\n")

    # 先拉数据
    print("[1/2] 拉取通胀预期数据...")
    fetch_series()

    # 计算
    print("\n[2/2] 计算通胀预期压力...")
    conn = sqlite3.connect(DB_PATH)
    try:
        def _load(sid, limit=120):
            df = pd.read_sql_query(
                f"SELECT timestamp, value FROM observations "
                f"WHERE series_id=? ORDER BY timestamp DESC LIMIT ?",
                conn, params=(sid, limit)
            )
            return df.sort_values('timestamp')['value'].astype(float)

        mich_1y = _load('MICH_1Y_EXPECT', 120)
        mich_5y = _load('MICH_5Y_EXPECT', 120)
        sentiment = _load('CONSUMER_SENTIMENT', 120)

        stress_score = 0.0
        details = []

        # 1年通胀预期
        if len(mich_1y) >= 1:
            exp_1y = float(mich_1y.iloc[-1])
            if exp_1y > 4.5:
                score = 30
                stress_score += score
                details.append(f"1Y通胀预期={exp_1y:.1f}% >4.5%（滞胀螺旋风险）, +{score}")
            elif exp_1y > 4.0:
                score = 15
                stress_score += score
                details.append(f"1Y通胀预期={exp_1y:.1f}% >4.0%, +{score}")

        # 5年通胀预期
        if len(mich_5y) >= 1:
            exp_5y = float(mich_5y.iloc[-1])
            if exp_5y > 3.5:
                score = 25
                stress_score += score
                details.append(f"5Y通胀预期={exp_5y:.1f}% >3.5%（长期锚定失效）, +{score}")
            elif exp_5y > 3.0:
                score = 10
                stress_score += score
                details.append(f"5Y通胀预期={exp_5y:.1f}% >3.0%, +{score}")

        # 消费者信心
        if len(sentiment) >= 2:
            s_now = float(sentiment.iloc[-1])
            s_prev = float(sentiment.iloc[-2])
            s_chg = s_now - s_prev
            if s_now < 50 and s_chg < -3:
                score = 20
                stress_score += score
                details.append(f"消费者信心={s_now:.1f} <50 且环比{s_chg:.1f}, +{score}")

        # 通胀预期 vs 消费者信心背离
        if len(mich_1y) >= 1 and len(sentiment) >= 1:
            exp_1y = float(mich_1y.iloc[-1])
            s_now = float(sentiment.iloc[-1])
            if exp_1y > 4.0 and s_now < 55:
                score = 15
                stress_score += score
                details.append(f"滞胀特征：通胀预期高({exp_1y:.1f}%)+信心低({s_now:.1f}), +{score}")

        stress_score = min(stress_score, 100)
        if stress_score >= 70:
            level = 'EXTREME'
        elif stress_score >= 50:
            level = 'HIGH'
        elif stress_score >= 30:
            level = 'MEDIUM'
        else:
            level = 'LOW'

        result = {
            'asof': asof,
            'inf_expect_stress': round(stress_score, 1),
            'level': level,
            'details': details,
        }
    finally:
        conn.close()

    # 落盘
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engine_inf_expect (
            asof_date TEXT PRIMARY KEY,
            stress_score REAL, level TEXT, detail TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO engine_inf_expect
        (asof_date, stress_score, level, detail)
        VALUES (?, ?, ?, ?)
    """, (asof, result['inf_expect_stress'], result['level'], json.dumps(details)))
    conn.commit()
    conn.close()

    print(f"\n  INF_EXPECT Stress: {result['inf_expect_stress']}/100 ({result['level']})")
    for d in details:
        print(f"    → {d}")
    print(f"{'='*60}\n")

    return result


if __name__ == "__main__":
    asof = datetime.now().strftime('%Y-%m-%d')
    compute_engine(asof)