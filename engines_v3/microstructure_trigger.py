# -*- coding: utf-8 -*-
"""engines_v3/microstructure_trigger.py - 微观结构扳机（多路径探测版）"""
import sqlite3
import pandas as pd
import json
import os
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'

def _find_csv(filename):
    """在 data/ 及其子目录中寻找 CSV 文件"""
    paths = [
        DATA_DIR / filename,
        DATA_DIR / 'lti' / filename,
        DATA_DIR / 'market' / filename,
        DATA_DIR / 'crypto' / filename,
        BASE_DIR / filename
    ]
    for p in paths:
        if p.exists():
            return p
    return None

def compute_microstructure_trigger(asof: str) -> dict:
    score = 0.0
    details = {}
    status = 'NORMAL'

    # 1. 期权维度 (Deribit Skew)
    try:
        p_skew = _find_csv('deribit_skew.csv')
        if p_skew:
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
            details['Options'] = 'CSV_Not_Found'
    except Exception as e:
        details['Options_Err'] = str(e)[:30]

    # 2. 订单流维度 (Hyperliquid 深度)
    try:
        p_depth = _find_csv('hyperliquid_depth.csv')
        if p_depth:
            df_depth = pd.read_csv(p_depth)
            if not df_depth.empty:
                btc_depth = df_depth[df_depth['coin'] == 'BTC']
                if not btc_depth.empty:
                    latest = btc_depth.iloc[-1]
                    imbalance = float(latest.get('bid_ask_imbalance', 0.0))
                    details['HL_BTC_Imbalance'] = round(imbalance, 3)
                    
                    if imbalance < -0.3:
                        score += 30
                    elif imbalance < -0.1:
                        score += 15
        else:
            details['Depth'] = 'CSV_Not_Found'
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