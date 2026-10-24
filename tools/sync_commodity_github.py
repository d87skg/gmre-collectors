# -*- coding: utf-8 -*-
"""tools/sync_commodity_github.py - 从 GitHub 拉取外盘商品数据并入库"""
import requests
import sqlite3
import csv
import io
from datetime import datetime

DB_PATH = 'data/macro.db'
GITHUB_CSV_URL = "https://raw.githubusercontent.com/d87skg/gmre-collectors/main/data/commodity_micro.csv"

def sync():
    print("🔄 正在从 GitHub 拉取外盘商品数据...")
    try:
        r = requests.get(f"{GITHUB_CSV_URL}?t={datetime.now().timestamp()}", timeout=15)
        r.raise_for_status()
        
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        if not rows:
            print("⚠️ 外盘 CSV 为空")
            return

        conn = sqlite3.connect(DB_PATH)
        count = 0
        for row in rows:
            date_str = row['date']
            symbol = row['symbol']
            price = float(row['close_price'])
            
            conn.execute(
                """INSERT OR REPLACE INTO commodity_caps 
                   (date, symbol, open_interest, warehouse_stock, close_price) 
                   VALUES (?, ?, NULL, NULL, ?)""",
                (date_str, symbol, price)
            )
            count += 1
            
        conn.commit()
        conn.close()
        print(f"💾 已同步 {count} 条外盘商品价格数据至 macro.db")
        
    except Exception as e:
        print(f"❌ 同步失败: {e}")

if __name__ == "__main__":
    sync()