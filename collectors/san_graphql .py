import requests
import os
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('SANPY_APIKEY')
API_URL = "https://api.santiment.net/graphql"

headers = {
    "Authorization": f"Apikey {API_KEY}",
    "Content-Type": "application/json"
}

def run_query(query):
    try:
        response = requests.post(API_URL, json={"query": query}, headers=headers, timeout=30)
        data = response.json()
        if "errors" in data:
            print(f"GraphQL 返回错误: {data['errors']}")
            return None
        return data.get("data", {})
    except Exception as e:
        print(f"请求异常: {e}")
        return None

# 1. 抓取社交情绪（Trending Words）
def get_trending_coins(size=10):
    query = f"""
    {{
      trendingWords(
        from: "2026-09-01T00:00:00Z"
        to: "2026-09-08T00:00:00Z"
        size: {size}
      ) {{
        datetime
        topWords {{
          word
          score
        }}
      }}
    }}
    """
    data = run_query(query)
    return data

# 2. 抓取 MVRV 历史数据（注意 Free 计划只能看 1 年前的数据）
def get_mvrv_data(slug="bitcoin", metric="mvrv_usd_1d"):
    query = f"""
    {{
      getMetric(metric: "{metric}") {{
        timeseriesData(
          slug: "{slug}"
          from: "2025-01-01T00:00:00Z"
          to: "2025-06-01T00:00:00Z"
          interval: "1d"
        ) {{
          datetime
          value
        }}
      }}
    }}
    """
    data = run_query(query)
    return data

if __name__ == "__main__":
    # 测试社交情绪数据
    trending = get_trending_coins()
    print("Trending Words:", trending)
    
    # 测试 MVRV 数据（注意结果可能是 1 年前的）
    mvrv = get_mvrv_data()
    print("MVRV Data:", mvrv)