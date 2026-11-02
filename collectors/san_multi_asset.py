import san
import os
import pandas as pd
import sqlite3
import datetime  # 新增：获取动态日期
from dotenv import load_dotenv

load_dotenv()
san.ApiConfig.api_key = os.getenv('SANPY_APIKEY')

if not san.ApiConfig.api_key:
    print("⚠️ 警告：请在 .env 文件中正确配置 SANPY_APIKEY！")
    exit()

def fetch_and_store():
    assets = ["bitcoin", "ethereum"]
    today = datetime.datetime.now().strftime('%Y-%m-%d')  # 新增：动态获取当前日期
    print(f"正在抓取 {assets} 的 DAU 数据...")
    all_data = pd.DataFrame()
    
    try:
        for asset in assets:
            daa_df = san.get(
                f"daily_active_addresses/{asset}", 
                from_date="2025-01-01", 
                to_date=today, # 修改：使用动态日期
                interval="1d"
            )
            # 核心代码：缩进对齐
            daa_df['metric'] = 'daily_active_addresses'
            daa_df['slug'] = asset
            daa_df = daa_df.reset_index()
            
            # 暂时跳过 nvt_ratio，因为旧版 sanpy 的接口已被废弃
            all_data = pd.concat([all_data, daa_df])
            
    except Exception as e:
        print(f"抓取失败: {e}")
        return

    conn = sqlite3.connect('data/macro.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS san_metrics (
            metric TEXT,
            slug TEXT,
            datetime TEXT,
            value REAL,
            PRIMARY KEY (metric, slug, datetime)
        )
    ''')
    
    for index, row in all_data.iterrows():
        c.execute(
            "INSERT OR REPLACE INTO san_metrics (metric, slug, datetime, value) VALUES (?, ?, ?, ?)",
            (row['metric'], row['slug'], str(row['datetime']), row['value'])
        )
    
    conn.commit()
    conn.close()
    print(f"✅ 数据已入库，共写入 {len(all_data)} 条记录。")

if __name__ == "__main__":
    fetch_and_store()