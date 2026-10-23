# -*- coding: utf-8 -*-
"""collectors/lme_commodity.py - 抓取外盘商品库存与价格（云端运行）"""
import csv
import os
import yfinance as yf
from datetime import datetime

SYMBOLS = {
    'LME_COPPER_PROXY': 'CPER',   # 美国铜指数 ETF
    'WTI_OIL_PROXY':    'USO',    # 原油 ETF
    'GOLD_PROXY':       'GLD',    # 黄金 ETF
}

def main():
    csv_path = 'data/commodity_micro.csv'
    os.makedirs('data', exist_ok=True)
    
    rows = []
    date_str = datetime.now().strftime('%Y-%m-%d')
    
    for name, ticker in SYMBOLS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="2d")
            if not hist.empty:
                latest_price = hist['Close'].iloc[-1]
                rows.append([date_str, name, latest_price])
                print(f"✅ {name} ({ticker}): {latest_price:.2f}")
        except Exception as e:
            print(f"❌ {name} 抓取失败: {e}")
            
    if rows:
        file_exists = os.path.isfile(csv_path)
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['date', 'symbol', 'close_price'])
            writer.writerows(rows)
        print(f"💾 已写入 {csv_path}")

if __name__ == '__main__':
    main()