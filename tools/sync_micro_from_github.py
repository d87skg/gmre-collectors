# -*- coding: utf-8 -*-
"""sync_micro_from_github.py - 从 GitHub CSV 同步微观数据入库（终极防锁版 + 源头安检）"""
import requests
import sqlite3
import csv
import io
import os
from datetime import datetime

# 强制使用当前执行目录的绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'macro.db')
GITHUB_CSV_URL = "https://raw.githubusercontent.com/d87skg/gmre-collectors/main/data/crypto_micro.csv"

def sync():
    print("🔄 正在从 GitHub 拉取微观数据...")
    try:
        r = requests.get(f"{GITHUB_CSV_URL}?t={datetime.now().timestamp()}", timeout=15)
        r.raise_for_status()
        
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        if not rows:
            print("⚠️ CSV 为空")
            return
            
        latest = rows[-1]
        date_str = latest['datetime'].split(' ')[0]
        
        # ================= 源头安检门 =================
        # 1. 提取 CB 溢价 (正常范围一般在 -5% 到 +5% 之间)
        cb_prem = None
        if latest.get('coinbase_premium'):
            val = float(latest['coinbase_premium'])
            if not (-10.0 <= val <= 10.0):
                print(f"🚨 [安检拦截] CB溢价异常 ({val}%)，强制舍弃！")
            else:
                cb_prem = val

        # 2. 提取 Bitget FR (年化正常在 -100% 到 +100% 之间，超过 150% 绝对算错)
        bit_fr = None
        if latest.get('bitget_funding'):
            val = float(latest['bitget_funding'])
            if not (-150.0 <= val <= 150.0):
                print(f"🚨 [安检拦截] Bitget FR异常 ({val}%)，强制舍弃！")
            else:
                bit_fr = val

        # 3. 提取多空比 (必须是正数)
        ls_ratio = None
        if latest.get('retail_long_short'):
            val = float(latest['retail_long_short'])
            if val < 0:
                print(f"🚨 [安检拦截] 多空比异常 ({val})，强制舍弃！")
            else:
                ls_ratio = val
        # ==============================================
            
        print(f"✅ 最新数据 [{date_str}]: CB溢价={cb_prem}, FR={bit_fr}, 多空比={ls_ratio}")

        # 使用 timeout 参数防止因锁死而永久卡住
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS crypto_micro (
                    asof_date TEXT PRIMARY KEY, coinbase_premium REAL, 
                    bitget_funding REAL, long_short_ratio REAL
                )
            """)
            conn.execute("""
                INSERT OR REPLACE INTO crypto_micro 
                (asof_date, coinbase_premium, bitget_funding, long_short_ratio) 
                VALUES (?, ?, ?, ?)
            """, (date_str, cb_prem, bit_fr, ls_ratio))
            conn.commit()
            print(f"💾 已同步至 {DB_PATH}")
        finally:
            conn.close()
        
    except Exception as e:
        print(f"❌ 同步失败: {e}")

if __name__ == "__main__":
    sync()