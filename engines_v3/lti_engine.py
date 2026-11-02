# -*- coding: utf-8 -*-
"""engines_v3/lti_engine.py - LTI 清算透明度引擎（v2: 加 Gold-Stock 维度）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'


def _get_pct(conn, column_name, current_val, reverse=False):
    try:
        df = pd.read_sql_query(
            f"SELECT {column_name} FROM feishu_snapshot WHERE {column_name} IS NOT NULL AND {column_name} != ''",
            conn
        )
        if len(df) < 5:
            return None
        vals = df[column_name].astype(float)
        if reverse:
            pct = (vals > current_val).mean() * 100
        else:
            pct = (vals < current_val).mean() * 100
        return round(pct, 1)
    except Exception:
        return None


def _load(conn, sid, limit=30):
    for col in ['timestamp', 'date']:
        try:
            df = pd.read_sql_query(
                f"SELECT {col} AS dt, value FROM observations WHERE series_id=? ORDER BY {col} DESC LIMIT ?",
                conn, params=(sid, limit)
            )
            if not df.empty:
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce')
                df = df.dropna(subset=['dt']).drop_duplicates(subset=['dt'], keep='first')
                return df.sort_values('dt').set_index('dt')['value'].astype(float)
        except Exception:
            continue
    return pd.Series(dtype=float)


def compute_lti(asof=None):
    asof_str = asof or datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1", conn)
        fr_row = conn.execute(
            "SELECT value FROM observations WHERE series_id='BTC_FUNDING_RATE_1H' ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        oi_rows = conn.execute(
            "SELECT value FROM observations WHERE series_id='BTC_OI_VALUE_HIST' ORDER BY timestamp DESC LIMIT 289"
        ).fetchall()
    finally:
        conn.close()

    if df.empty:
        return {'status': 'NoData', 'lti_score': 0, 'level': 'UNKNOWN', 'details': {}}

    latest = df.iloc[0]

    def to_f(v):
        try:
            return float(v) if pd.notna(v) and str(v) != '' else 0.0
        except Exception:
            return 0.0

    fr_cross = to_f(latest.get('fr_cross_diff'))
    bitget_fr = to_f(latest.get('bitget_btc_fr'))
    hl_imb = to_f(latest.get('hl_imbalance_btc'))

    scores = {}
    active_weights = {}
    details = {}

    # 1. 跨所差异
    if fr_cross != 0.0:
        scores['FR_Divergence'] = min(max(fr_cross * 5, 0), 100)
        active_weights['FR_Divergence'] = 0.25
        details['FR_Divergence'] = f"{scores['FR_Divergence']} (观测)"
    else:
        scores['FR_Divergence'] = None
        active_weights['FR_Divergence'] = 0.0
        details['FR_Divergence'] = "MISSING_DATA"

    # 2. 极端费率
    if bitget_fr != 0.0:
        s2 = min(abs(bitget_fr), 100)
        scores['FR_Extreme'] = s2
        active_weights['FR_Extreme'] = 0.25
        details['FR_Extreme'] = f"{s2:.1f} (观测)"
    else:
        scores['FR_Extreme'] = None
        active_weights['FR_Extreme'] = 0.0
        details['FR_Extreme'] = "MISSING_DATA"

    # 3. 持仓变化
    if len(oi_rows) >= 289 and oi_rows[288][0]:
        current_oi = oi_rows[0][0]
        prev_oi = oi_rows[288][0]
        oi_change = (current_oi - prev_oi) / prev_oi * 100
        s3 = min(abs(oi_change) * 10, 100)
        scores['OI_Fragility'] = s3
        active_weights['OI_Fragility'] = 0.25
        details['OI_Fragility'] = f"{s3:.1f} (观测)"
    else:
        scores['OI_Fragility'] = None
        active_weights['OI_Fragility'] = 0.0
        details['OI_Fragility'] = "MISSING_DATA"

    # 4. 🆕 Gold-Stock 流动性联动
    try:
        conn2 = sqlite3.connect(DB_PATH)
        try:
            gold = _load(conn2, 'GOLD_PRICE', 30)
            spx = _load(conn2, 'SP500', 30)
        finally:
            conn2.close()

        if len(gold) >= 5 and len(spx) >= 5:
            gold_5d = (float(gold.iloc[-1]) - float(gold.iloc[-5])) / float(gold.iloc[-5])
            spx_5d = (float(spx.iloc[-1]) - float(spx.iloc[-5])) / float(spx.iloc[-5])

            # 黄金跌幅 > 美股跌幅 x 2 → 流动性抛售模式
            if gold_5d < 0 and abs(gold_5d) > abs(spx_5d) * 2:
                s4 = min(abs(gold_5d) * 1000, 100)
                mode = 'LIQ_SELL'
            # 黄金涨 + 美股跌 → 避险模式
            elif gold_5d > 0 and spx_5d < 0:
                s4 = 30.0
                mode = 'RISK_OFF_SAFE'
            else:
                s4 = 20.0
                mode = 'NORMAL'

            scores['Gold_Stock'] = s4
            active_weights['Gold_Stock'] = 0.25
            details['Gold_Stock'] = f"{s4:.1f} ({mode})"
        else:
            scores['Gold_Stock'] = None
            active_weights['Gold_Stock'] = 0.0
            details['Gold_Stock'] = "MISSING_DATA"
    except Exception:
        scores['Gold_Stock'] = None
        active_weights['Gold_Stock'] = 0.0
        details['Gold_Stock'] = "ERROR"

    total_weight = sum(active_weights.values())
    if total_weight <= 0:
        return {'status': 'AllMissing', 'lti_score': 0, 'level': 'UNKNOWN', 'details': details, 'raw': {}}

    lti_score = 0.0
    for k, w in active_weights.items():
        if w > 0:
            lti_score += scores[k] * (w / total_weight)

    lti_score = min(max(lti_score, 0), 100)

    if lti_score >= 80:
        level = "EXTREME"
    elif lti_score >= 60:
        level = "HIGH"
    elif lti_score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS lti_engine (
        asof_date TEXT PRIMARY KEY, lti_score REAL, level TEXT)""")
    conn.execute("""INSERT OR REPLACE INTO lti_engine
        (asof_date, lti_score, level) VALUES (?, ?, ?)""",
        (asof_str, lti_score, level))
    conn.commit()
    conn.close()

    return {
        'asof': asof_str,
        'lti_score': round(lti_score, 1),
        'level': level,
        'details': details,
        'raw': {'bitget_fr': bitget_fr, 'hl_imbalance': hl_imb, 'fr_cross_diff': fr_cross}
    }


if __name__ == "__main__":
    res = compute_lti()
    print(f"\n{'='*50}")
    print(f"  LTI 清算透明度引擎 - {res.get('asof', 'N/A')}")
    print(f"{'='*50}\n")
    print(f"  LTI 评分: {res['lti_score']}/100 ({res['level']})")
    for k, v in res['details'].items():
        print(f"    ├─ {k}: {v}")
    print(f"{'='*50}\n")