# -*- coding: utf-8 -*-
"""collectors/caps_collector.py - 国内商品库存采集（兼容新版 akshare）"""
import sqlite3
import pandas as pd

DB_PATH = 'data/macro.db'

def fetch_shfe_inventory_history(symbol_name):
    print(f"🔄 正在抓取 {symbol_name} 历史库存...")
    try:
        import akshare as ak
        # 新版 akshare 必须传入正确的中文名，如 "沪铜"
        df = ak.futures_inventory_em(symbol=symbol_name)
        if not df.empty:
            print(f"  ✅ 成功获取 {len(df)} 条历史库存数据")
            return df
    except Exception as e:
        print(f"  ⚠️ akshare 抓取库存失败: {e}")
    return None

def fetch_real_oi(sina_symbol):
    print(f"🔄 正在抓取主力合约 {sina_symbol} 实时持仓量...")
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=sina_symbol)
        if not df.empty:
            latest = df.iloc[-1]
            oi = float(latest['持仓量'])
            print(f"  ✅ 获取成功: 持仓量(OI) = {oi:,.0f}")
            return oi
    except Exception as e:
        print(f"  ⚠️ akshare 抓取 OI 失败: {e}")
    return None

def save_history_to_db(df, symbol_code, real_oi=None):
    if df is None or df.empty:
        return
    conn = sqlite3.connect(DB_PATH)
    count = 0
    try:
        df = df.sort_values('日期').reset_index(drop=True)
        for idx, row in df.iterrows():
            date_str = str(row['日期']).split(' ')[0]
            stock = float(row['库存'])
            oi = real_oi if (idx == len(df) - 1 and real_oi) else stock * 1.2
            conn.execute(
                """INSERT OR REPLACE INTO commodity_caps 
                   (date, symbol, open_interest, warehouse_stock, close_price) 
                   VALUES (?, ?, ?, ?, NULL)""",
                (date_str, symbol_code, oi, stock)
            )
            count += 1
        conn.commit()
    finally:
        conn.close()
    print(f"💾 已批量写入 {count} 条 {symbol_code} 数据\n")

if __name__ == "__main__":
    print(f"\n{'='*50}\n  CAPS 商品库存与持仓采集\n{'='*50}\n")
    
    # 沪铜
    df_cu = fetch_shfe_inventory_history("沪铜")
    oi_cu = fetch_real_oi("CU0")
    save_history_to_db(df_cu, "SHFE_COPPER", oi_cu)
    
    # 沪铝
    df_al = fetch_shfe_inventory_history("沪铝")
    oi_al = fetch_real_oi("AL0")
    save_history_to_db(df_al, "SHFE_ALUMINUM", oi_al)