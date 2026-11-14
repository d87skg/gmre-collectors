# -*- coding: utf-8 -*-
"""collectors/realtime_market.py - 实时行情覆写 (v4.1 适配)"""
import requests
import sqlite3
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                meta = result[0].get('meta', {})
                price = meta.get('regularMarketPrice')
                ts = meta.get('regularMarketTime')
                if price and ts:
                    dt = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                    return float(price), dt
    except Exception as e:
        print(f"  ❌ {symbol} 获取失败: {e}")
    return None, None

def update_db():
    print("  🔄 开始拉取 SP500 实时数据...")
    spx_price, spx_date = fetch_yahoo('^GSPC')
    if spx_price:
        print(f"    ✅ [Yahoo 成功] SP500: {spx_price:.2f} ({spx_date})")
    else:
        print("    ⚠️ SP500 获取失败")

    print("  🔄 开始拉取 VIX 实时数据...")
    vix_price, vix_date = fetch_yahoo('^VIX')
    if vix_price:
        print(f"    ✅ [Yahoo 成功] VIX: {vix_price:.2f} ({vix_date})")
    else:
        print("    ⚠️ VIX 获取失败")

    if spx_price or vix_price:
        conn = sqlite3.connect(DB_PATH)
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 🆕 适配虚拟列（替换 timestamp 为 obs_ts）
        if spx_price:
            conn.execute("INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                         ('SP500', spx_date, spx_date, spx_price, 'rt_Yahoo'))
        if vix_price:
            conn.execute("INSERT OR REPLACE INTO observations (series_id, obs_ts, obs_date, value, source, ingest_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                         ('VIX', vix_date, vix_date, vix_price, 'rt_Yahoo'))
        conn.commit()
        conn.close()
        print("  🎯 已强制覆写数据库!")

if __name__ == '__main__':
    update_db()