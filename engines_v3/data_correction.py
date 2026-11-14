# -*- coding: utf-8 -*-
"""engines_v3/data_correction.py - 数据修正 (v4.1: 真增量 + 极速超时版)"""
import os
import sys
import requests
import pandas as pd
import io
from datetime import datetime
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import Database

DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

# 🆕 增加核心CPI (CPILFESL) 和 美联储资产负债表 (WALCL)，广义美元 (DTWEXBGS)
FRED_SERIES = {
    'SP500': 'SP500', 'DCOILWTICO': 'WTI_OIL', 'DCOILBRENTEU': 'BRENT_OIL',
    'PPIACO': 'PPI', 'PAYEMS': 'PAYROLLS', 'UNRATE': 'UNEMPLOYMENT',
    'ICSA': 'JOBLESS_CLAIMS', 'BAMLH0A0HYM2': 'HY_SPREAD',
    'DGS10': 'YC10Y', 'DGS2': 'YC2Y', 'DGS30': 'YC30Y',
    'VIXCLS': 'VIX', 'RRPONTSYD': 'RRPONTSYD', 'WTREGEN': 'WTREGEN',
    'CPILFESL': 'CPI_CORE',         
    'CPIAUCSL': 'CPI',              
    'WALCL': 'FED_BALANCE_SHEET',   
    'DTWEXBGS': 'BROAD_DOLLAR',     
}

def get_latest_date(conn, local_id):
    try:
        row = conn.execute("SELECT MAX(obs_date) FROM observations WHERE series_id=?", (local_id,)).fetchone()
        if row and row[0]: return str(row[0])
    except Exception: pass
    return None

def fetch_fred_series(series_id, local_id, db_conn):
    latest_date = get_latest_date(db_conn, local_id)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code != 200: return []
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        
        if latest_date:
            df = df[df['date'] > latest_date]
        return df.to_dict('records')
    except Exception: return []

def process_fred():
    db = Database(DB_PATH)
    raw_conn = sqlite3.connect(DB_PATH)
    success_count = 0
    
    for fred_id, local_id in FRED_SERIES.items():
        data = fetch_fred_series(fred_id, local_id, raw_conn)
        if not data: continue
        for row in data:
            db.insert_observation(local_id, row['date'], row['value'], source='FRED_API')
        latest = data[-1]
        print(f"  ✅ {fred_id:15s} -> {local_id:20s} {len(data)}条新增  {latest['date']} = {latest['value']}")
        success_count += 1
        
    raw_conn.close()
    db.conn.close()
    return success_count

def process_gold():
    print("\n  [GOLD] 启动三源交叉验证...")
    try:
        r = requests.get("https://hq.sinajs.cn/list=hf_GC", headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        if r.status_code == 200:
            val = float(r.text.split('"')[1].split(',')[0])
            db = Database(DB_PATH)
            db.insert_observation('GOLD_PRICE', datetime.now().strftime('%Y-%m-%d'), val, source='sina_hf_GC')
            db.conn.close()
            print(f"    ✅ GOLD_PRICE = {val:.2f}")
            return True
    except Exception: pass
    return False

def main():
    print(f"\n{'='*60}\n  数据修正 (v4.1: 真增量 + 极速超时)\n{'='*60}\n")
    success = process_fred()
    process_gold()
    print(f"\n✅ 数据修正完成：成功 {success} 组\n{'='*60}\n")

if __name__ == "__main__":
    main()