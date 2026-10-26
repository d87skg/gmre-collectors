# -*- coding: utf-8 -*-
"""engines_v3/lti_engine.py - LTI 清算透明度引擎（接入本地历史金矿修复版）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'

def compute_lti(asof=None):
    """计算 LTI 清算透明度指数 (0-100)"""
    asof_str = asof or datetime.now().strftime('%Y-%m-%d')
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. 从历史库读取最新的资金费率 (取 1000 条用于计算历史分位)
        fr_df = pd.read_sql_query("SELECT timestamp, value FROM observations WHERE series_id='BTC_FUNDING_RATE_1H' ORDER BY timestamp DESC LIMIT 1000", conn)
        
        # 2. 读取最新的持仓量 (取 1000 条，因为它是 5m 级别，1000条约等于 3.5 天)
        oi_df = pd.read_sql_query("SELECT timestamp, value FROM observations WHERE series_id='BTC_OI_VALUE_HIST' ORDER BY timestamp DESC LIMIT 1000", conn)
        
        # 3. 降级备选：飞书快照
        fallback_row = conn.execute("SELECT bitget_btc_fr, hl_imbalance_btc FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1").fetchone()
    finally:
        conn.close()

    score = 0.0
    details = {}
    raw_data = {}

    # ================= 核心计算逻辑 =================
    if not fr_df.empty:
        # --- 资金费率极值 ---
        # 将原始费率转换为年化百分比 (假设是 8 小时费率: 0.0001 * 3 * 365 * 100 = 10.95%)
        fr_df['annualized'] = fr_df['value'] * 3 * 365 * 100
        fr_df['abs_fr'] = fr_df['annualized'].abs()
        
        current_fr = fr_df['annualized'].iloc[0]
        current_abs_fr = fr_df['abs_fr'].iloc[0]
        
        # 计算绝对年化费率在当前历史中的分位
        pct_fr_ext = (fr_df['abs_fr'] < current_abs_fr).mean() * 100
        s2 = pct_fr_ext if pct_fr_ext > 0 else 10
        details['FR_Extreme'] = f"{round(s2, 1)} (历史分位)"
        
        raw_data['bitget_fr'] = current_fr 
    else:
        # 降级：读飞书快照
        if fallback_row:
            current_fr = float(fallback_row[0]) if fallback_row[0] else 0.0
            if abs(current_fr) > 30: s2 = 100
            elif abs(current_fr) > 15: s2 = 70
            elif abs(current_fr) > 5: s2 = 30
            else: s2 = 10
            details['FR_Extreme'] = f"{s2} (绝对值降级)"
            raw_data['bitget_fr'] = current_fr
        else:
            s2 = 0
            details['FR_Extreme'] = "0 (无数据)"
            raw_data['bitget_fr'] = 0.0

    # --- 持仓量变化 ---
    if not oi_df.empty and len(oi_df) > 300: 
        current_oi = oi_df['value'].iloc[0]
        # 因为是 5m 级别，288 条就是 24 小时前
        oi_24h_ago = oi_df['value'].iloc[288] 
        oi_change_pct = (current_oi - oi_24h_ago) / oi_24h_ago * 100 if oi_24h_ago else 0
        
        # 持仓剧烈变化作为风险参考
        if abs(oi_change_pct) > 10: s3 = 100
        elif abs(oi_change_pct) > 5: s3 = 70
        elif abs(oi_change_pct) > 2: s3 = 40
        else: s3 = 10
        details['OI_Change'] = f"{s3} (24H变幅 {oi_change_pct:+.2f}%)"
        raw_data['hl_imbalance'] = oi_change_pct 
    else:
        # 降级
        hl_imb = float(fallback_row[1]) if fallback_row and fallback_row[1] else 0.0
        if hl_imb < -0.5: s3 = 100
        elif hl_imb < -0.2: s3 = 70
        elif hl_imb < 0.0: s3 = 40
        else: s3 = 10
        details['Book_Fragility'] = f"{s3} (绝对值降级)"
        raw_data['hl_imbalance'] = hl_imb

    # 跨所费率差异暂时用静态
    s1 = 40
    details['FR_Divergence'] = "40 (静态占位)"
    
    score = (s1 * 0.3) + (s2 * 0.3) + (s3 * 0.4)
    lti_score = min(score, 100)

    if lti_score >= 80: level = "EXTREME"
    elif lti_score >= 60: level = "HIGH"
    elif lti_score >= 40: level = "MEDIUM"
    else: level = "LOW"

    # 落表
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lti_engine (
            asof_date TEXT PRIMARY KEY, lti_score REAL, level TEXT
        )
    """)
    conn.execute("""
        INSERT OR REPLACE INTO lti_engine (asof_date, lti_score, level) 
        VALUES (?, ?, ?)
    """, (asof_str, lti_score, level))
    conn.commit()
    conn.close()

    # 兼容 run_v4.py 的打印字段
    raw_data['fr_cross_diff'] = 0.0 # 静态占位

    return {
        'asof': asof_str,
        'lti_score': round(lti_score, 1),
        'level': level,
        'details': details,
        'raw': raw_data
    }

if __name__ == "__main__":
    res = compute_lti()
    print(f"\n{'='*50}")
    print(f"  LTI 清算透明度引擎 - {res.get('asof', 'N/A')}")
    print(f"{'='*50}\n")
    print(f"  LTI 评分: {res['lti_score']}/100 ({res['level']})")
    for k, v in res['details'].items():
        print(f"    ├─ {k}: {v}")
    print(f"\n  原始数据: {res['raw']}")
    print(f"{'='*50}\n")