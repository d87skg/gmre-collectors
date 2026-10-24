"""engines_v3/engine_inf_expect.py - 通胀预期引擎（全链条审计版）"""
import requests
import sqlite3
import io
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'
PROXIES = None

INF_EXPECT_SERIES = {
    'MICH':     'MICH_1Y_EXPECT',
    'T5YIE':    'T5YIE_5Y_EXPECT',
    'UMCSENT':  'CONSUMER_SENTIMENT',
}

def fetch_series():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    status_map = {}
    fetched_values = {}

    for fred_id, local_id in INF_EXPECT_SERIES.items():
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fred_id}"
            r = requests.get(url, timeout=30, proxies=PROXIES)
            if r.status_code != 200:
                status_map[fred_id] = False
                continue
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = ['date', 'value']
            df = df[df['value'] != '.']
            if df.empty:
                status_map[fred_id] = False
                continue
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
            latest_val = float(df.iloc[-1]['value'])
            fetched_values[fred_id] = latest_val
            status_map[fred_id] = True
        except Exception as e:
            status_map[fred_id] = False

    conn.commit()
    conn.close()
    return count, status_map, fetched_values

def compute_engine(asof: str) -> dict:
    print(f"\n{'='*60}")
    print(f"  INF_EXPECT Engine - {asof}")
    print(f"{'='*60}\n")
    print("[1/2] 拉取通胀预期数据...")
    _, status_map, fetched = fetch_series()

    if not status_map.get('MICH') and not status_map.get('T5YIE'):
        return {'asof': asof, 'inf_expect_stress': -1, 'level': 'MISSING_DATA'}

    print("\n[2/2] 计算通胀预期压力 (明细审计)...")
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
        t5yie_5y = _load('T5YIE_5Y_EXPECT', 120)
        sentiment = _load('CONSUMER_SENTIMENT', 120)

        stress_score = 0.0
        details = []
        
        # 打印头部
        print(f"  {'指标':<12} | {'原始值':<8} | {'阈值':<12} | {'得分':<6} | {'状态'}")
        print(f"  {'-'*12}-+-{'-'*8}-+-{'-'*12}-+-{'-'*6}-+-{'-'*8}")

        # 1. 1年通胀预期
        if len(mich_1y) >= 1:
            exp_1y = float(mich_1y.iloc[-1])
            score = 0
            status = "正常"
            if exp_1y >= 4.5:
                score = 30
                status = "极高"
            elif exp_1y >= 4.001:
                score = 15
                status = "偏高"
            stress_score += score
            details.append(f"1Y调查通胀={exp_1y:.3f}%, 得分+{score}")
            print(f"  {'MICH_1Y':<12} | {exp_1y:>8.3f} | {'>=4.5(极高)':<12} | {score:>6} | {status}")

        # 2. 5年通胀预期 (市场隐含)
        if len(t5yie_5y) >= 1:
            exp_5y = float(t5yie_5y.iloc[-1])
            score = 0
            status = "正常"
            if exp_5y >= 3.5:
                score = 25
                status = "极高"
            elif exp_5y >= 3.001:
                score = 10
                status = "偏高"
            stress_score += score
            details.append(f"5Y市场通胀={exp_5y:.3f}%, 得分+{score}")
            print(f"  {'T5YIE_5Y':<12} | {exp_5y:>8.3f} | {'>=3.5(极高)':<12} | {score:>6} | {status}")

        # 3. 消费者信心
        if len(sentiment) >= 2:
            s_now = float(sentiment.iloc[-1])
            s_prev = float(sentiment.iloc[-2])
            s_chg = s_now - s_prev
            score = 0
            status = "正常"
            if s_now < 50 and s_chg < -3:
                score = 20
                status = "极弱"
            elif s_now < 55:
                status = "偏弱(未扣分)"
            stress_score += score
            details.append(f"信心={s_now:.1f}, 得分+{score}")
            print(f"  {'UMCSENT':<12} | {s_now:>8.1f} | {'<50且降>3':<12} | {score:>6} | {status}")

        stress_score = min(stress_score, 100)
        if stress_score >= 70: level = 'EXTREME'
        elif stress_score >= 50: level = 'HIGH'
        elif stress_score >= 30: level = 'MEDIUM'
        else: level = 'LOW'

        result = {
            'asof': asof,
            'inf_expect_stress': round(stress_score, 1),
            'level': level,
            'details': details,
        }
    finally:
        conn.close()

    print(f"\n  📊 基础得分累加: {stress_score:.1f} / 100")
    print(f"  INF_EXPECT Stress: {result['inf_expect_stress']}/100 ({result['level']})")
    print(f"{'='*60}\n")
    return result

if __name__ == "__main__":
    compute_engine(datetime.now().strftime('%Y-%m-%d'))