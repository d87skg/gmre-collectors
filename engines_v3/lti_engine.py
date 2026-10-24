# -*- coding: utf-8 -*-
"""engines_v3/lti_engine.py - LTI 清算透明度引擎（历史分位驱动版）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'

def _get_pct(conn, column_name, current_val, reverse=False):
    """
    从 feishu_snapshot 表计算历史分位。
    reverse=True 表示数值越低，风险越高（如盘口不平衡）。
    如果历史数据少于 5 条，返回 None（触发降级逻辑）。
    """
    try:
        df = pd.read_sql_query(
            f"SELECT {column_name} FROM feishu_snapshot WHERE {column_name} IS NOT NULL AND {column_name} != ''",
            conn
        )
        if len(df) < 5:
            return None
            
        vals = df[column_name].astype(float)
        if reverse:
            # 数值越低，分位越高（例如：不平衡 -0.5 比 -0.1 危险）
            pct = (vals > current_val).mean() * 100
        else:
            # 数值越高，分位越高
            pct = (vals < current_val).mean() * 100
            
        return round(pct, 1)
    except Exception:
        return None

def compute_lti(asof=None):
    """计算 LTI 清算透明度指数 (0-100)"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM feishu_snapshot ORDER BY timestamp DESC LIMIT 1", conn)
    finally:
        conn.close()
        
    if df.empty:
        return {'status': 'NoData', 'lti_score': 0, 'level': 'UNKNOWN'}
        
    latest = df.iloc[0]
    
    def to_f(v): 
        try: return float(v) if pd.notna(v) and str(v) != '' else 0.0
        except: return 0.0
        
    fr_cross = to_f(latest.get('fr_cross_diff'))
    bitget_fr = to_f(latest.get('bitget_btc_fr'))
    hl_imb = to_f(latest.get('hl_imbalance_btc'))
    
    score = 0.0
    details = {}
    
    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. 跨所资金费率差异 (权重 30%)
        # 优先使用历史分位，如果数据不够（<5条），降级使用绝对阈值
        pct_fr = _get_pct(conn, 'fr_cross_diff', fr_cross, reverse=False)
        if pct_fr is not None:
            s1 = pct_fr
            details['FR_Divergence'] = f"{s1} (分位)"
        else:
            if fr_cross > 20: s1 = 100
            elif fr_cross > 10: s1 = 70
            elif fr_cross > 5: s1 = 40
            else: s1 = 10
            details['FR_Divergence'] = f"{round(s1, 1)} (绝对值)"
        score += s1 * 0.3
        
        # 2. 极端资金费率 (权重 30%)
        # 取绝对值计算分位，无论正负极端都算拥挤
        pct_fr_ext = _get_pct(conn, 'bitget_btc_fr', abs(bitget_fr), reverse=False)
        if pct_fr_ext is not None:
            s2 = pct_fr_ext
            details['FR_Extreme'] = f"{s2} (分位)"
        else:
            if abs(bitget_fr) > 30: s2 = 100
            elif abs(bitget_fr) > 15: s2 = 70
            elif abs(bitget_fr) > 5: s2 = 30
            else: s2 = 10
            details['FR_Extreme'] = f"{round(s2, 1)} (绝对值)"
        score += s2 * 0.3
        
        # 3. 订单簿买盘枯竭度 (权重 40%)
        # reverse=True：越负越危险（如 -0.5 比 +0.2 危险）
        pct_imb = _get_pct(conn, 'hl_imbalance_btc', hl_imb, reverse=True)
        if pct_imb is not None:
            s3 = pct_imb
            details['Book_Fragility'] = f"{s3} (分位)"
        else:
            if hl_imb < -0.5: s3 = 100
            elif hl_imb < -0.2: s3 = 70
            elif hl_imb < 0.0: s3 = 40
            else: s3 = 10
            details['Book_Fragility'] = f"{round(s3, 1)} (绝对值)"
        score += s3 * 0.4
        
        lti_score = min(score, 100)
    finally:
        conn.close()
    
    # 评级
    if lti_score >= 80: level = "EXTREME"
    elif lti_score >= 60: level = "HIGH"
    elif lti_score >= 40: level = "MEDIUM"
    else: level = "LOW"
    
    # 落表
    asof_str = asof or datetime.now().strftime('%Y-%m-%d')
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
    
    return {
        'asof': asof_str,
        'lti_score': round(lti_score, 1),
        'level': level,
        'details': details,
        'raw': {
            'fr_cross_diff': fr_cross,
            'bitget_fr': bitget_fr,
            'hl_imbalance': hl_imb
        }
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