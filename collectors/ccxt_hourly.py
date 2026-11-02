import ccxt
import sqlite3
import pandas as pd
import datetime

# 如果你有代理（比如 Clash 默认端口7890），请在这里修改端口
PROXY_URL = "http://127.0.0.1:7890"  

def fetch_and_store_1h():
    # 优先使用 OKX
    try:
        exchange = ccxt.okx({
            'proxies': {
                'http': PROXY_URL,
                'https': PROXY_URL,
            },
            'timeout': 15000  # 延长超时时间
        })
        print("正在通过代理连接 OKX...")
        ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=500)
    except Exception as e:
        print(f"OKX失败，尝试 Bybit: {e}")
        try:
            exchange = ccxt.bybit({
                'proxies': {
                    'http': PROXY_URL,
                    'https': PROXY_URL,
                },
                'timeout': 15000
            })
            ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=500)
        except Exception as e2:
            print(f"Bybit也失败，系统将继续使用日频 CMC 数据: {e2}")
            return

    # 整理数据
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['slug'] = 'bitcoin'

    # 存入独立小时级数据表
    conn = sqlite3.connect('data/macro.db')
    df[['datetime', 'slug', 'open', 'high', 'low', 'close', 'volume']].to_sql(
        'asset_prices_1h', 
        conn, 
        if_exists='append', 
        index=False
    )
    conn.close()
    print(f"✅ 小时级数据已入库，共写入 {len(df)} 条记录。")

if __name__ == "__main__":
    fetch_and_store_1h()