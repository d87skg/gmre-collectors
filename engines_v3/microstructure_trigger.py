# -*- coding: utf-8 -*-
"""engines_v3/microstructure_trigger.py - 微观结构扳机（CSV读取版）"""
import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'data' / 'macro.db'

def compute_microstructure_trigger(asof: str) -> dict:
    score = 0.0
    details = {}
    status = 'NORMAL'

    # 1. 期权维度 (Deribit Skew)
    try:
        p_skew = BASE_DIR / 'data' / 'deribit_skew.csv'
        if p_skew.exists():
            df = pd.read_csv(p_skew)
            if not df.empty:
                latest = df.iloc[-1]
                btc_rr25 = float(latest.get('rr25', 0.0))
                btc_pcr = float(latest.get('pcr', 0.5))
                
                details['BTC_RR25'] = round(btc_rr25, 4)
                details['BTC_PCR'] = round(btc_pcr, 3)
                
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
        p_depth = BASE_DIR / 'data' / 'hyperliquid_depth.csv'
        if p_depth.exists():
            df_depth = pd.read_csv(p_depth)
            if not df_depth.empty:
                btc_depth = df_depth[df_depth['coin'] == 'BTC']
                if not btc_depth.empty:
                    latest = btc_depth.iloc[-1]  # 取最后一行
                    imbalance = float(latest.get('bid_ask_imbalance', 0.0))
                    details['HL_BTC_Imbalance'] = round(imbalance, 3)
                    
                    if imbalance < -0.3:
                        score += 30
                    elif imbalance < -0.1:
                        score += 15
        else:
            details['Depth'] = 'NoCSV'
    except Exception as e:
        details['Depth_Err'] = str(e)[:30]

    if score >= 50:
        status = 'CRITICAL'
    elif score >= 30:
        status = 'WARNING'

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