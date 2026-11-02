# -*- coding: utf-8 -*-
"""tools/check_freshness.py - 数据新鲜度检查（兼容 observations 表）"""
import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'data/macro.db'

# SLA 定义 (最大允许滞后的天数)
SLA = {
    'SP500': 3, 'WTI_OIL': 3, 'GOLD_PRICE': 3, 'USD_JPY': 3, 'VIX': 3,
    'HY_SPREAD': 3, 'SOFR': 3, 'EFFR': 3, 'RRP_BALANCE': 3, 'TGA_BALANCE': 3,
    'RESERVE_BALANCE': 7, 'YC10Y': 3, 'YC2Y': 3
}

def main():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    print(f"{'series':15s} {'latest':12s} {'lag':>5s} {'sla':>5s} {'status'}")
    print("-" * 55)
    
    now = datetime.now()
    for sid, sla_days in SLA.items():
        # 直接从 observations 表查最新数据（不再依赖 series_history）
        row = conn.execute(
            "SELECT MAX(timestamp) FROM observations WHERE series_id=?", (sid,)
        ).fetchone()
        
        if not row or not row[0]:
            print(f"{sid:15s} {'无数据':12s} {'-':>5s} {sla_days:>5d} ❌ 缺失")
            continue
            
        latest_str = row[0].split(' ')[0].split('T')[0]
        try:
            latest_date = datetime.strptime(latest_str, '%Y-%m-%d')
            lag = (now - latest_date).days
            status = "✅ 正常" if lag <= sla_days else "⚠️ 过期"
            print(f"{sid:15s} {latest_str:12s} {lag:>5d} {sla_days:>5d} {status}")
        except Exception:
            print(f"{sid:15s} {latest_str:12s} {'异常':>5s} {sla_days:>5d} ❌ 格式错误")
            
    conn.close()

if __name__ == '__main__':
    main()