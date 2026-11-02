# tools/download_long_history.py
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime

DB_PATH = 'data/macro.db'
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 我们一次性补全这几个核心资产的超长历史
targets = {
    '^GSPC': 'SP500_HISTORY',  # 标普500 (几十年)
    'GC=F': 'GOLD_HISTORY',   # 黄金期货 (几十年)
    'BTC-USD': 'BTC_PRICE_HISTORY', # 比特币 (10年+)
    'ETH-USD': 'ETH_PRICE_HISTORY'  # 以太坊 (7年+)
}

for symbol, series_id in targets.items():
    print(f"⏳ 正在下载 {symbol} ({series_id}) ...")
    try:
        # 下载全量历史数据，interval=1d
        df = yf.download(symbol, period='max', interval='1d', progress=False)
        
        if df.empty:
            print(f"❌ {symbol} 下载失败，可能被限流")
            continue
            
        # 清洗数据
        df = df.reset_index()
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # 批量写入数据库（使用 INSERT OR IGNORE，不覆盖已有数据）
        count = 0
        for _, row in df.iterrows():
            date_str = row['Date']
            # 取收盘价
            if isinstance(row['Close'], pd.Series):
                close_price = float(row['Close'].iloc[0]) # 处理 yfinance 多列问题
            else:
                close_price = float(row['Close'])
                
            cursor.execute("""
                INSERT OR IGNORE INTO observations (series_id, timestamp, value, source, retrieved_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            """, (series_id, date_str, close_price, 'yfinance_hist'))
            count += 1
            
        conn.commit()
        print(f"✅ {series_id} 成功写入 {count} 条数据！")
        
    except Exception as e:
        print(f"❌ {symbol} 报错: {e}")

conn.close()
print("🎉 历史数据补全完成！")