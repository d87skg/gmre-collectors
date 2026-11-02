import san
import pandas as pd
import sqlite3

# 配置你的 Santiment API Key
san.ApiConfig.api_key = "你的真实API密钥"

def fetch_and_store():
    # 1. 批量抓取数据（省额度）
    assets = ["bitcoin", "ethereum"]
    
    print(f"正在抓取 {assets} 的 DAU 和 NVT 数据...")
    # 抓取每日活跃地址数（返回宽表，列名是资产slug）
    daa_df = san.get_many(metric="daily_active_addresses", slugs=assets, from_date="2024-01-01", to_date="2026-09-07", interval="1d")
    # 抓取 NVT 比率（返回宽表）
    nvt_df = san.get_many(metric="nvt_ratio", slugs=assets, from_date="2024-01-01", to_date="2026-09-07", interval="1d")
    
    # 2. 数据清洗与宽表转窄表（适配数据库结构）
    # 将宽表 melt 成长表：index=date, variable=slug, value=value
    daa_long = daa_df.reset_index().melt(id_vars='datetime', var_name='slug', value_name='value')
    daa_long['metric'] = 'daily_active_addresses'
    
    nvt_long = nvt_df.reset_index().melt(id_vars='datetime', var_name='slug', value_name='value')
    nvt_long['metric'] = 'nvt_ratio'
    
    # 合并所有数据
    all_data = pd.concat([daa_long, nvt_long])
    
    # 3. 连接数据库并设置防重复入库逻辑 (INSERT OR REPLACE)
    conn = sqlite3.connect('data/macro.db')
    c = conn.cursor()
    
    # 创建表，设置唯一约束防止无限膨胀
    c.execute('''
        CREATE TABLE IF NOT EXISTS san_metrics (
            metric TEXT,
            slug TEXT,
            datetime TEXT,
            value REAL,
            PRIMARY KEY (metric, slug, datetime)
        )
    ''')
    
    # 将数据写入数据库 (存在相同的组合则替换，避免重复)
    print("正在写入数据库...")
    all_data.to_sql('san_metrics', conn, if_exists='replace', index=False) 
    # 注意：直接使用 INSERT OR REPLACE 会更稳妥，但 pandas to_sql 不支持直接指定
    # 我们可以用以下方式手动插入：
    
    # 使用 INSERT OR REPLACE 语法插入数据
    for index, row in all_data.iterrows():
        c.execute(
            "INSERT OR REPLACE INTO san_metrics (metric, slug, datetime, value) VALUES (?, ?, ?, ?)",
            (row['metric'], row['slug'], row['datetime'], row['value'])
        )
    
    conn.commit()
    conn.close()
    print(f"✅ 数据已入库，共写入 {len(all_data)} 条记录，避免了重复数据的堆积。")

if __name__ == "__main__":
    fetch_and_store()