import requests
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()
AV_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')

def fetch_macro_data():
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TREASURY_YIELD",
        "interval": "daily",
        "maturity": "10year",
        "apikey": AV_API_KEY
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        rates = data.get("data", [])
        if not rates:
            print(f"AV 返回异常: {data}")
            return

        # 只取最新一条数据
        latest = rates[0]
        record = {
            'series_id': 'market:YC10Y_AV',
            'value': float(latest['value']),
            'datetime': latest['date']
        }

        # 存入独立表 av_metrics，避免和原 observations 表冲突
        conn = sqlite3.connect('data/macro.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS av_metrics (
                series_id TEXT,
                datetime TEXT,
                value REAL,
                PRIMARY KEY (series_id, datetime)
            )
        ''')
        c.execute('''
            INSERT OR REPLACE INTO av_metrics (series_id, datetime, value) VALUES (?, ?, ?)
        ''', (record['series_id'], record['datetime'], record['value']))
        conn.commit()
        conn.close()
        print(f"✅ AV 宏观数据入库成功: {record['series_id']} = {record['value']}%")
    except Exception as e:
        print(f"AV 请求异常: {e}")

if __name__ == "__main__":
    fetch_macro_data()