import requests
import sqlite3
import pandas as pd
import time
import os
from dotenv import load_dotenv

load_dotenv()

# ============ 可选：代理配置（如果你有梯子，填入端口后取消注释） ============
PROXY_URL = None  # 例如 "http://127.0.0.1:7890"
# PROXY_URL = "http://127.0.0.1:7890"

proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

# 通用请求头，模拟浏览器访问，降低被拦截概率
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json"
}

def fetch_from_coingecko(coin_id, retries=3):
    """从 CoinGecko 抓取，带自动重试"""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": "30", "interval": "hourly"}
    
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, 
                                     proxies=proxies, timeout=20)
            data = response.json()
            prices = data.get('prices', [])
            volumes = data.get('total_volumes', [])
            if prices:
                return prices, volumes
        except Exception as e:
            print(f"    CoinGecko 第 {attempt+1} 次尝试失败: {str(e)[:80]}")
            time.sleep(3)
    return None, None

def fetch_from_cryptocompare(coin_symbol, retries=2):
    """备用方案：CryptoCompare 免费 API（国内通常可直连）"""
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": coin_symbol, "tsym": "USD", "limit": 720}  # 720小时=30天
    
    for attempt in range(retries):
        try:
            response = requests.get(url, params=params, headers=HEADERS, 
                                     proxies=proxies, timeout=20)
            data = response.json()
            rows = data.get('Data', {}).get('Data', [])
            if rows:
                prices = [[r['time'] * 1000, r['close']] for r in rows]
                volumes = [[r['time'] * 1000, r['volumeto']] for r in rows]
                return prices, volumes
        except Exception as e:
            print(f"    CryptoCompare 第 {attempt+1} 次尝试失败: {str(e)[:80]}")
            time.sleep(3)
    return None, None

def fetch_coingecko_hourly():
    # CoinGecko 用 id，CryptoCompare 用 symbol
    coins = [
        {"id": "bitcoin",  "symbol": "BTC"},
        {"id": "ethereum", "symbol": "ETH"},
        {"id": "solana",   "symbol": "SOL"},
    ]
    
    conn = sqlite3.connect('data/macro.db')
    
    for coin in coins:
        coin_id = coin["id"]
        coin_sym = coin["symbol"]
        prices, volumes = None, None
        source = ""

        # ---- 第一优先：CoinGecko ----
        print(f"正在抓取 {coin_id} (CoinGecko)...")
        prices, volumes = fetch_from_coingecko(coin_id)
        if prices:
            source = "CoinGecko"
        else:
            # ---- 第二优先：CryptoCompare 备用 ----
            print(f"  ⚠️ CoinGecko 失败，切换到 CryptoCompare...")
            prices, volumes = fetch_from_cryptocompare(coin_sym)
            if prices:
                source = "CryptoCompare"

        if not prices:
            print(f"❌ {coin_id} 所有数据源均失败，跳过")
            continue

        try:
            df = pd.DataFrame(prices, columns=['timestamp', 'close'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            vol_df = pd.DataFrame(volumes, columns=['timestamp', 'volume'])
            df = df.merge(vol_df, on='timestamp', how='left')
            
            df['slug'] = coin_id
            df['open'] = df['close']
            df['high'] = df['close']
            df['low'] = df['close']
            df['volume'] = df['volume'].fillna(0)
            
            df[['datetime', 'slug', 'open', 'high', 'low', 'close', 'volume']].to_sql(
                'asset_prices_1h', conn, if_exists='append', index=False
            )
            print(f"✅ {coin_id} ({source}) 入库成功，共 {len(df)} 条")
            time.sleep(2)  # 防止被限流
            
        except Exception as e:
            print(f"❌ {coin_id} 数据处理失败: {e}")
    
    # 清理90天前的旧数据，防止数据库膨胀
    conn.execute("DELETE FROM asset_prices_1h WHERE datetime < datetime('now', '-90 days')")
    conn.commit()
    conn.close()
    print("🎉 所有币种数据抓取完成！")

if __name__ == "__main__":
    fetch_coingecko_hourly()