import requests
import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

# 加载 .env 中的 Key
load_dotenv()
API_KEY = os.getenv('SANPY_APIKEY')
API_URL = "https://api.santiment.net/graphql"

headers = {
    "Authorization": f"Apikey {API_KEY}",
    "Content-Type": "application/json"
}

# 查询社交情绪（Social Volume Total）的历史数据
def fetch_social_volume(slug="bitcoin"):
    query = f"""
    {{
      getMetric(metric: "social_volume_total") {{
        timeseriesData(
          slug: "{slug}"
          from: "2025-09-08T00:00:00Z"
to: "2026-08-09T00:00:00Z"
          interval: "1d"
        ) {{
          datetime
          value
        }}
      }}
    }}
    """
    try:
        response = requests.post(API_URL, json={"query": query}, headers=headers, timeout=30)
        data = response.json()
        if "errors" in data:
            print(f"GraphQL 报错: {data['errors']}")
            return None
        # 提取数据
        rows = data.get("data", {}).get("getMetric", {}).get("timeseriesData", [])
        return rows
    except Exception as e:
        print(f"请求异常: {e}")
        return None

def save_to_db(rows):
    if not rows:
        print("没有获取到数据，可能是免费版权限受限（只能看一年前）。")
        return
    
    # 整理为 DataFrame
    df = pd.DataFrame(rows)
    df['datetime'] = pd.to_datetime(df['datetime']).dt.date
    df['slug'] = 'bitcoin'
    df['metric'] = 'social_volume_total'
    
    # 写入数据库 san_metrics 表
    conn = sqlite3.connect('data/macro.db')
    df.to_sql('san_metrics', conn, if_exists='append', index=False)
    conn.close()
    print(f"✅ 社交情绪数据已入库，共 {len(df)} 条记录。")

if __name__ == "__main__":
    print("正在抓取 BTC 社交情绪数据（2025年上半年，免费版可访问区）...")
    data = fetch_social_volume()
    save_to_db(data)