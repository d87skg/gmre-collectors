# -*- coding: utf-8 -*-
"""engines_v3/microstructure_trigger.py - 微观结构扳机（期权 + 订单流）"""
import sqlite3
import pandas as pd
import json
from datetime import datetime

DB_PATH = 'data/macro.db'

def compute_microstructure_trigger(asof: str) -> dict:
    """
    结合 Deribit 期权 Skew/PCR 与 Hyperliquid 订单流，判断是否发生微结构破裂。
    """
    score = 0.0
    details = {}
    status = 'NORMAL'

    try:
        # 1. 期权维度 (Deribit Skew)
        try:
            # 读取最新一次采集的 deribit_skew
            p = 'data/deribit_skew.csv'
            import os
            if os.path.exists(p):
                df = pd.read_csv(p)
                if not df.empty:
                    latest = df.iloc[-1]
                    btc_rr25 = float(latest.get('rr25', 0.0))
                    btc_pcr = float(latest.get('pcr', 0.5))
                    
                    details['BTC_RR25'] = round(btc_rr25, 4)
                    details['BTC_PCR'] = round(btc_pcr, 3)
                    
                    # 极端负偏斜（看跌期权极贵）或 PCR 飙升
                    if btc_rr25 < -0.05:  # 负偏斜
                        score += 30
                    if btc_pcr > 1.5:
                        score += 20
            else:
                details['Options'] = 'NoCSV'
        except Exception as e:
            details['Options_Err'] = str(e)[:30]

        # 2. 订单流维度 (Hyperliquid 深度)
        try:
            conn = sqlite3.connect(DB_PATH)
            df_depth = pd.read_sql_query("SELECT * FROM hyperliquid_depth ORDER BY rowid DESC LIMIT 2", conn)
            conn.close()
            
            if not df_depth.empty:
                # 我们只看 BTC 的盘口不平衡度
                btc_depth = df_depth[df_depth['coin'] == 'BTC']
                if not btc_depth.empty:
                    latest = btc_depth.iloc[0]
                    imbalance = float(latest['bid_ask_imbalance'])
                    details['HL_BTC_Imbalance'] = round(imbalance, 3)
                    
                    # 极度卖压
                    if imbalance < -0.3:
                        score += 30
                    elif imbalance < -0.1:
                        score += 15
        except Exception as e:
            details['Depth_Err'] = str(e)[:30]

        # 综合判定
        if score >= 50:
            status = 'CRITICAL'
        elif score >= 30:
            status = 'WARNING'

    except Exception as e:
        print(f"  ⚠️ 微观结构扳机计算异常: {e}")

    return {
        'asof': asof,
        'score': min(score, 100),
        'status': status,
        'details': details
    }

if __name__ == '__main__':
    asof = datetime.now().strftime('%Y-%m-%d')
    r = compute_microstructure_trigger(asof)
    print(f"\n{'='*60}")
    print(f"  微观结构扳机 - {asof}")
    print(f"{'='*60}")
    print(f"  状态: {r['status']} | 评分: {r['score']}/100")
    print(f"  详情: {r['details']}")
    print(f"{'='*60}\n")