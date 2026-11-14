# -*- coding: utf-8 -*-
"""engines_v3/data_correction.py - 数据修正 (v4.2: 主源优先 + 备用源自动降级)"""
import os
import sys
import requests
import pandas as pd
import io
from datetime import datetime
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import Database
from collectors.fallback_collectors import (
    fetch_tencent_realtime, fetch_akshare_index_us, 
    fetch_akshare_forex, fetch_akshare_commodity
)

DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')

FRED_SERIES = {
    'SP500': 'SP500', 'DCOILWTICO': 'WTI_OIL', 'DCOILBRENTEU': 'BRENT_OIL',
    'PPIACO': 'PPI', 'PAYEMS': 'PAYROLLS', 'UNRATE': 'UNEMPLOYMENT',
    'ICSA': 'JOBLESS_CLAIMS', 'BAMLH0A0HYM2': 'HY_SPREAD',
    'DGS10': 'YC10Y', 'DGS2': 'YC2Y', 'DGS30': 'YC30Y',
    'VIXCLS': 'VIX', 'RRPONTSYD': 'RRPONTSYD', 'WTREGEN': 'WTREGEN',
    'CPILFESL': 'CPI_CORE', 'CPIAUCSL': 'CPI', 'WALCL': 'FED_BALANCE_SHEET',
    'DTWEXBGS': 'BROAD_DOLLAR',
}

# 🆕 备用映射：主源挂掉时，用哪个备用接口
FALLBACK_MAP = {
    'SP500': ('tencent', 'usINX'),
    'WTI_OIL': ('tencent', 'hf_CL'),
    'GOLD_PRICE': ('tencent', 'hf_GC'),
    'VIX': ('tencent', 'usVIX'),
    'USD_JPY': ('tencent', 'fx_susdjpy'),
    'USD_CNH': ('tencent', 'fx_susdcnh'),
}

def get_latest_date(conn, local_id):
    try:
        row = conn.execute("SELECT MAX(obs_date) FROM observations WHERE series_id=?", (local_id,)).fetchone()
        if row and row[0]: return str(row[0])
    except Exception: pass
    return None

def fetch_fred_with_fallback(series_id, local_id, db_conn):
    """核心逻辑：先试主源 FRED，失败则降级到备用源"""
    latest_local = get_latest_date(db_conn, local_id)
    
    # 1. 主源：FRED
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            df = pd.read_csv(io.StringIO(r.text))
            df.columns = ['date', 'value']
            df = df[df['value'] != '.']
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df['value'] = pd.to_numeric(df['value'], errors='coerce')
            df = df.dropna()
            if latest_local:
                df = df[df['date'] > latest_local]
            rows = df.to_dict('records')
            for row in rows: row['source'] = 'FRED_API'
            return rows, 'primary'
    except Exception as e:
        pass # 静默失败，进入备用源

    # 2. 备用源：根据映射选择
    if series_id in FALLBACK_MAP or local_id in FALLBACK_MAP:
        fallback_key = FALLBACK_MAP.get(local_id) or FALLBACK_MAP.get(series_id)
        if fallback_key:
            source_type, symbol = fallback_key
            print(f"  🔄 [FALLBACK] {local_id} 主源失败，尝试备用源 {source_type}:{symbol}")
            
            if source_type == 'tencent':
                res = fetch_tencent_realtime(symbol)
                if res:
                    if latest_local and res['date'] <= latest_local:
                        print(f"    ⏭️ 备用源 {local_id} 日期 {res['date']} 已存在，跳过")
                        return [], 'fallback'
                    return [{'date': res['date'], 'value': res['value'], 'source': 'tencent_fallback'}], 'fallback'
    
    # 如果备用源也失败，返回空
    return [], 'failed'

def process_fred():
    db = Database(DB_PATH)
    raw_conn = sqlite3.connect(DB_PATH)
    success_count, fallback_count = 0, 0
    
    for fred_id, local_id in FRED_SERIES.items():
        data, mode = fetch_fred_with_fallback(fred_id, local_id, raw_conn)
        
        if not data:
            continue
        
        for row in data:
            # 🆕 如果来源是备用源，在写入时标记，以便 LTI 和报表追溯
            source = row.get('source', 'FRED_API')
            db.insert_observation(local_id, row['date'], row['value'], source=source)
        
        latest = data[-1]
        if mode == 'primary':
            print(f"  ✅ {fred_id:15s} -> {local_id:20s} {len(data)}条新增 (主源)")
            success_count += 1
        else:
            print(f"  🟡 {fred_id:15s} -> {local_id:20s} {len(data)}条新增 (备用源: {latest['source']})")
            fallback_count += 1
            
    raw_conn.close()
    db.conn.close()
    return success_count, fallback_count

def process_gold():
    print("\n  [GOLD] 启动三源交叉验证...")
    try:
        r = requests.get("https://hq.sinajs.cn/list=hf_GC", headers={"Referer": "https://finance.sina.com.cn"}, timeout=5)
        if r.status_code == 200:
            val = float(r.text.split('"')[1].split(',')[0])
            db = Database(DB_PATH)
            db.insert_observation('GOLD_PRICE', datetime.now().strftime('%Y-%m-%d'), val, source='sina_hf_GC')
            db.conn.close()
            print(f"    ✅ GOLD_PRICE = {val:.2f} (主源)")
            return True
    except Exception: pass
    
    # 降级到腾讯
    res = fetch_tencent_realtime('hf_GC')
    if res:
        db = Database(DB_PATH)
        db.insert_observation('GOLD_PRICE', res['date'], res['value'], source='tencent_fallback')
        db.conn.close()
        print(f"    🟡 GOLD_PRICE = {res['value']:.2f} (备用源: 腾讯)")
        return True
    
    print("    ❌ 黄金所有源失败")
    return False

def main():
    print(f"\n{'='*60}\n  数据修正 (v4.2: 主源优先 + 备用源降级)\n{'='*60}\n")
    success, fallback = process_fred()
    process_gold()
    print(f"\n✅ 数据修正完成：主源成功 {success} 组 | 备用源降级 {fallback} 组\n{'='*60}\n")

if __name__ == "__main__":
    main()