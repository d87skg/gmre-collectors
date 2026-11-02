# tools/import_crypto_history.py
import pandas as pd
import sqlite3
import os
from datetime import datetime

DB_PATH = 'data/macro.db'
# 统一使用 full 版（测试发现 v3 和 full 数据完全一致，避免重复）
BASE_DIR = r'D:\btc_carry_full'

def import_parquet_to_db(file_path, series_map):
    if not os.path.exists(file_path):
        print(f"⚠️ 文件不存在: {file_path}")
        return
        
    print(f"📂 正在处理: {os.path.basename(file_path)}")
    df = pd.read_parquet(file_path)
    
    # 统一时间戳处理
    if 'dt' in df.columns:
        df['dt'] = pd.to_datetime(df['dt'])
    elif 'create_time' in df.columns:
        df['dt'] = pd.to_datetime(df['create_time'], unit='ms') # 假设是毫秒时间戳
    else:
        print("❌ 找不到时间列 (dt 或 create_time)")
        return

    df = df.sort_values('dt').drop_duplicates(subset=['dt'], keep='last')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    total_inserted = 0
    for col, series_id in series_map.items():
        if col not in df.columns:
            continue
            
        records = []
        for _, row in df.iterrows():
            if pd.isna(row[col]):
                continue
            
            # 时间格式化为 YYYY-MM-DD HH:MM:SS (如果是日线，可以只截取前10位)
            ts_str = row['dt'].strftime('%Y-%m-%d %H:%M:%S') 
            
            records.append((series_id, ts_str, float(row[col]), 'parquet_hist', datetime.now().isoformat()))
            
        if records:
            cursor.executemany("""
                INSERT OR IGNORE INTO observations (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, ?)
            """, records)
            print(f"  ✅ 已写入 {series_id:<25} | {len(records)} 条")
            total_inserted += len(records)

    conn.commit()
    conn.close()
    return total_inserted

# --- 1. 导入 btc_merged (核心微观数据) ---
merged_map = {
    'close': 'BTC_SPOT_PRICE_1H',
    'perp_close': 'BTC_PERP_PRICE_1H',
    'basis': 'BTC_BASIS_1H',
    'fundingRate': 'BTC_FUNDING_RATE_1H'
}
import_parquet_to_db(os.path.join(BASE_DIR, 'btc_merged.parquet'), merged_map)

# --- 2. 导入 1h 现货与合约量 ---
spot_map = {'close': 'BTC_SPOT_HIST_1H', 'volume': 'BTC_SPOT_VOLUME_1H'}
perp_map = {'close': 'BTC_PERP_HIST_1H', 'volume': 'BTC_PERP_VOLUME_1H'}
import_parquet_to_db(os.path.join(BASE_DIR, 'spot_1h.parquet'), spot_map)
import_parquet_to_db(os.path.join(BASE_DIR, 'perp_1h.parquet'), perp_map)

# --- 3. 导入 2026 衍生品指标 (多空比与持仓量) ---
# 假设里面有多个币种，我们需要过滤出 BTC
metrics_path = os.path.join(BASE_DIR, 'metrics_2026.parquet')
if os.path.exists(metrics_path):
    print("📂 正在处理: metrics_2026.parquet (需过滤 BTC)")
    df_metrics = pd.read_parquet(metrics_path)
    # 打印一下看看有哪些 symbol，通常是大写的 BTCUSDT
    # print(df_metrics['symbol'].unique())
    df_btc = df_metrics[df_metrics['symbol'].str.contains('BTC', case=False, na=False)]
    
    metrics_map = {
        'sum_open_interest_value': 'BTC_OI_VALUE_HIST', # 持仓量(名义价值)
        'sum_toptrader_long_short_ratio': 'BTC_TOP_LS_RATIO', # 大户多空比
        'sum_taker_long_short_vol_ratio': 'BTC_TAKER_LS_RATIO', # 吃单多空比
    }
    import_parquet_to_db(metrics_path.replace('metrics_2026.parquet', 'temp_btc_metrics.parquet'), metrics_map) if False else None
    # 因为上面的函数会读整个文件，我们直接在这里写特殊处理
    df_btc['dt'] = pd.to_datetime(df_btc['create_time'], unit='ms')
    df_btc = df_btc.sort_values('dt').drop_duplicates(subset=['dt'], keep='last')
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for col, sid in metrics_map.items():
        records = [(sid, row['dt'].strftime('%Y-%m-%d %H:%M:%S'), float(row[col]), 'parquet_hist', datetime.now().isoformat()) 
                   for _, row in df_btc.iterrows() if not pd.isna(row[col])]
        if records:
            cursor.executemany("INSERT OR IGNORE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, ?)", records)
            print(f"  ✅ 已写入 {sid:<25} | {len(records)} 条")
    conn.commit()
    conn.close()

print("🎉 历史加密数据入库完成！")