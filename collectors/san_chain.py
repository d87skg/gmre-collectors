import san
import pandas as pd
from sqlalchemy import create_engine

# 配置 API Key (从 .env 读取)
san.ApiConfig.api_key = "你的真实API密钥"

# 2. 抓取链上数据 (以 BTC 为例)
# 获取每日活跃地址数
daa_df = san.get(
    metric="daily_active_addresses", 
    slug="bitcoin", 
    from_date="2026-01-01", 
    to_date="2026-09-07", 
    interval="1d"
)
# 获取 NVT 比率 (注意：该指标会返回两个值：基于流通量和交易量)[citation:15]
nvt_df = san.get(
    metric="nvt_ratio", 
    slug="bitcoin", 
    from_date="2026-01-01", 
    to_date="2026-09-07", 
    interval="1d"
)

# 3. 清洗并处理数据
# DAA 返回的是 value 列，NVT 返回的是多列[citation:1][citation:15]
nvt_df = nvt_df.rename(columns={'nvtRatioCirculation': 'nvt_circulation'})
daa_df = daa_df.rename(columns={'value': 'daily_active_addresses'})

# 4. 数据入库 (写入 macro.db)
engine = create_engine('sqlite:///data/macro.db')
daa_df.to_sql('san_metrics', engine, if_exists='append', index=True)
nvt_df.to_sql('san_metrics', engine, if_exists='append', index=True)

print("✅ 链上交互与 NVT 数据已入库")