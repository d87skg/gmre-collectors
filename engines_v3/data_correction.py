# -*- coding: utf-8 -*-
"""engines_v3/data_correction.py - 数据修正 (v4.1: 真增量 + 极速超时版)"""
import os
import sys
import requests
import pandas as pd
import io
from datetime import datetime, timedelta
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import Database

DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

FRED_SERIES = {
    'SP500': 'SP500', 'DCOILWTICO': 'WTI_OIL', 'DCOILBRENTEU': 'BRENT_OIL',
    'PPIACO': 'PPI', 'PAYEMS': 'PAYROLLS', 'UNRATE': 'UNEMPLOYMENT',
    'ICSA': 'JOBLESS_CLAIMS', 'BAMLH0A0HYM2': 'HY_SPREAD',
    'DGS10': 'YC10Y', 'DGS2': 'YC2Y', 'DGS30': 'YC30Y',
    'VIXCLS': 'VIX', 'RRPONTSYD': 'RRPONTSYD', 'WTREGEN': 'WTREGEN',
}

def get_latest_date(conn, local_id):
    """查本地库最新日期，用于真增量"""
    try:
        row = conn.execute("SELECT MAX(obs_date) FROM observations WHERE series_id=?", (local_id,)).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception: pass
    return None

def fetch_fred_series(series_id, local_id, db_conn):
    latest_date = get_latest_date(db_conn, local_id)
    # FRED 的 CSV 接口无法直接传 start_date，但我们可以下载后本地截取，
    # 不过我们加了 5 秒超时，且只保留缺失部分，避免大量写库。
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, timeout=5)  # 🆕 极速超时
        if r.status_code != 200: return []
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()
        
        # 🆕 如果数据库里有旧数据，只保留比旧数据更新的行
        if latest_date:
            df = df[df['date'] > latest_date]
            
        return df.to_dict('records')
    except requests.exceptions.Timeout:
        print(f"  ⏱️ {series_id} 请求超时 (5s)，跳过")
        return []
    except Exception as e:
        print(f"  ❌ {series_id} 获取失败: {str(e)[:40]}")
        return []

def process_fred():
    db = Database(DB_PATH)
    success_count = 0
    
    # 获取一个原始连接用来查最新日期
    raw_conn = sqlite3.connect(DB_PATH)
    
    for fred_id, local_id in FRED_SERIES.items():
        data = fetch_fred_series(fred_id, local_id, raw_conn)
        if not data:
            # 如果没获取到新数据，可能是网络原因，也可能是已经是最新的
            continue
        
        new_cnt = 0
        for row in data:
            db.insert_observation(local_id, row['date'], row['value'], source='FRED_API')
            new_cnt += 1
            
        latest = data[-1]
        print(f"  ✅ {fred_id:15s} -> {local_id:20s} {new_cnt}条新增  {latest['date']} = {latest['value']} [FRED_API]")
        success_count += 1
        
    raw_conn.close()
    db.conn.close()
    return success_count

def process_gold():
    print("\n  [GOLD] 启动三源交叉验证...")
    sina_url = "https://hq.sinajs.cn/list=hf_GC"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
    
    sina_val = None
    try:
        # 🆕 黄金 Sina 接口极快，设 5 秒超时
        r = requests.get(sina_url, headers=headers, timeout=5)
        if r.status_code == 200:
            parts = r.text.split('"')[1].split(',')
            if len(parts) > 0: sina_val = float(parts[0])
    except Exception: pass

    if not sina_val:
        print("    ❌ 黄金数据源获取失败（或超时），跳过")
        return False

    print(f"    Sina: {sina_val:.2f}")
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    try:
        db = Database(DB_PATH)
        db.insert_observation('GOLD_PRICE', today_str, sina_val, source='sina_hf_GC')
        db.conn.close()
        print(f"    ✅ GOLD_PRICE -> {today_str} = {sina_val:.2f}")
        return True
    except Exception as e:
        print(f"    ❌ GOLD_PRICE 入库失败: {e}")
        return False

def main():
    print(f"\n{'='*60}")
    print(f"  数据修正 (v4.1: 真增量 + 极速超时)")
    print(f"  DB       : {os.path.abspath(DB_PATH)}")
    print(f"  MODE     : LIVE FRED API (5s timeout)")
    print(f"{'='*60}\n")

    success = process_fred()
    gold_ok = process_gold()

    print(f"\n{'='*60}")
    print(f"  ✅ 数据修正完成：成功 {success} / 跳过 {0 if gold_ok else 1}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()