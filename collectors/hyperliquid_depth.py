import requests
import pandas as pd
import time
from datetime import datetime, timezone
from pathlib import Path

INFO_URL = 'https://api.hyperliquid.xyz/info'

def fetch_depth(coin='BTC'):
    payload = {'type': 'l2Book', 'coin': coin}
    for attempt in range(3):
        try:
            res = requests.post(INFO_URL, json=payload, timeout=10)
            if res.status_code == 200: return res.json()
        except: time.sleep(2)
    return None

def calc_depth_metrics(data, levels=20):
    if not data or 'levels' not in data: return None
    bids, asks = data['levels']
    if not bids or not asks: return None
    best_bid, best_ask = float(bids[0]['px']), float(asks[0]['px'])
    mid = (best_bid + best_ask) / 2
    total_bid = sum(float(b['sz']) for b in bids[:levels])
    total_ask = sum(float(a['sz']) for a in asks[:levels])
    d2_bid = sum(float(b['sz']) for b in bids if float(b['px']) >= mid * (1 - 0.02))
    d2_ask = sum(float(a['sz']) for a in asks if float(a['px']) <= mid * (1 + 0.02))
    return {
        'coin': data.get('coin', ''),
        'mid': mid,
        'bid_ask_imbalance': (total_bid - total_ask) / (total_bid + total_ask) if (total_bid + total_ask) > 0 else 0,
        'd2_bid': d2_bid, 'd2_ask': d2_ask
    }

def main():
    rows = []
    for coin in ['BTC', 'ETH']:
        data = fetch_depth(coin)
        m = calc_depth_metrics(data)
        if m: rows.append(m)
    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/hyperliquid_depth.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条深度数据至 data/hyperliquid_depth.csv')

if __name__ == '__main__':
    main()