# -*- coding: utf-8 -*-
"""engines_v3/caps_engine.py - CAPS 商品逼仓引擎（落表版）"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = 'data/macro.db'

def compute_caps_risk(symbol):
    """计算单一品种的逼仓风险"""
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            f"SELECT * FROM commodity_caps WHERE symbol=? ORDER BY date DESC LIMIT 60",
            conn, params=(symbol,)
        )
    finally:
        conn.close()
    
    if df.empty:
        return None
        
    latest = df.iloc[0]
    stock = latest['warehouse_stock']
    oi = latest['open_interest']
    
    # 1. 虚实盘比
    ratio = (oi / stock) if (stock and stock > 0 and oi and oi > 0) else 0
    
    # 2. 库存分位
    if len(df) > 2:
        stock_series = df['warehouse_stock']
        pct = (stock_series < stock).mean() * 100
    else:
        pct = 50.0
        
    # 3. 综合评分
    score = 0.0
    if ratio > 10: score += 40
    elif ratio > 5: score += 25
    elif ratio > 3: score += 10
        
    if pct < 10: score += 60
    elif pct < 20: score += 40
    elif pct < 40: score += 20
        
    final_score = min(score, 100)
    
    return {
        'symbol': symbol,
        'date': latest['date'],
        'open_interest': oi,
        'warehouse_stock': stock,
        'oi_stock_ratio': round(ratio, 2),
        'stock_percentile': round(pct, 1),
        'caps_score': final_score
    }

def compute_all():
    print(f"\n{'='*60}")
    print(f"  CAPS 商品逼仓引擎 - {pd.Timestamp.now().strftime('%Y-%m-%d')}")
    print(f"{'='*60}\n")
    
    symbols = ['SHFE_COPPER', 'SHFE_ALUMINUM']
    asof = datetime.now().strftime('%Y-%m-%d')
    
    # 建表
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS caps_engine (
            asof_date TEXT, symbol TEXT, caps_score REAL, 
            oi_stock_ratio REAL, stock_percentile REAL,
            PRIMARY KEY (asof_date, symbol)
        )
    """)
    
    for sym in symbols:
        res = compute_caps_risk(sym)
        if res:
            icon = "🚨" if res['caps_score'] > 60 else "🟡" if res['caps_score'] > 30 else "🟢"
            print(f"  [{sym}] {icon}")
            print(f"    最新日期:        {res['date']}")
            print(f"    虚实盘比:        {res['oi_stock_ratio']}")
            print(f"    库存分位:        {res['stock_percentile']}%")
            print(f"    🚨 逼仓评分:     {res['caps_score']}/100\n")
            
            # 写入数据库
            conn.execute(
                """INSERT OR REPLACE INTO caps_engine 
                   (asof_date, symbol, caps_score, oi_stock_ratio, stock_percentile) 
                   VALUES (?, ?, ?, ?, ?)""",
                (asof, sym, res['caps_score'], res['oi_stock_ratio'], res['stock_percentile'])
            )
        else:
            print(f"  [{sym}] ❌ 数据不足\n")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    compute_all()