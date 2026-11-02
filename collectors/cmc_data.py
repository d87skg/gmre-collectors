import requests
import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
CMC_API_KEY = os.getenv('CMC_API_KEY')

headers = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': CMC_API_KEY
}

def fetch_market_data():
    # 获取 BTC 的实时市值、交易量和流通供应量
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    params = {"symbol": "BTC,ETH", "convert": "USD"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        if response.status_code != 200:
            print(f"CMC 接口报错: {data.get('status', {}).get('error_message')}")
            return

        rows = []
        for symbol, info in data['data'].items():
            quote = info['quote']['USD']
            rows.append({
                'slug': symbol.lower(),  # 转为小写，与已有系统匹配
                'market_cap': quote['market_cap'],
                'volume_24h': quote['volume_24h'],
                'percent_change_24h': quote['percent_change_24h']
            })
        
        # 存入数据库（建议新建表 CMC_MARKET_DATA）
        conn = sqlite3.connect('data/macro.db')
        df = pd.DataFrame(rows)
        df.to_sql('cmc_market_data', conn, if_exists='replace', index=False)
        conn.close()
        print("✅ CMC 全球市值数据已入库！")
    except Exception as e:
        print(f"CMC 请求异常: {e}")

if __name__ == "__main__":
    fetch_market_data()