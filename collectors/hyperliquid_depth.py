import requests
import time
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

INFO_URL = 'https://api.hyperliquid.xyz/info'

def fetch_depth(coin='BTC'):
    payload = {'type': 'l2Book', 'coin': coin}
    for attempt in range(3):
        try:
            res = requests.post(INFO_URL, json=payload, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            print(f'  {coin} 请求异常: {e}')
        time.sleep(2)
    return None

    best_bid = float(bids[0]['px'])
    best_ask = float(asks[0]['px'])
    mid = (best_bid + best_ask) / 2

    bid_sizes = [float(b['sz']) for b in bids[:levels]]
    ask_sizes = [float(a['sz']) for a in asks[:levels]]

    total_bid = sum(bid_sizes)
    total_ask = sum(ask_sizes)

    # 距现价 1%、2%、5% 的累计深度
    def depth_within(pct):
        bid_sum = sum(float(b['sz']) for b in bids if float(b['px']) >= mid * (1 - pct))
        ask_sum = sum(float(a['sz']) for a in asks if float(a['px']) <= mid * (1 + pct))
        return bid_sum, ask_sum

    d1_bid, d1_ask = depth_within(0.01)
    d2_bid, d2_ask = depth_within(0.02)
    d5_bid, d5_ask = depth_within(0.05)

    return {
        'coin': data.get('coin', ''),
        'mid': mid,
        'total_bid': total_bid,
        'total_ask': total_ask,
        'bid_ask_imbalance': (total_bid - total_ask) / (total_bid + total_ask) if (total_bid + total_ask) > 0 else 0,
        'd1_bid': d1_bid, 'd1_ask': d1_ask,
        'd2_bid': d2_bid, 'd2_ask': d2_ask,
        'd5_bid': d5_bid, 'd5_ask': d5_ask,
        'as_of': datetime.now(timezone.utc).isoformat(),
    }

def main():
    rows = []
    for coin in ['BTC', 'ETH']:
        try:
            data = fetch_depth(coin)
            m = calc_depth_metrics(data)
            if m:
                rows.append(m)
                print(f'{coin}: mid={m["mid"]:.2f}, imbalance={m["bid_ask_imbalance"]:+.3f}')
        except Exception as e:
            print(f'{coin} 失败: {e}')

    if rows:
        df = pd.DataFrame(rows)
        Path('data').mkdir(exist_ok=True)
        df.to_csv('data/hyperliquid_depth.csv', index=False)
        print(f'✅ 已保存 {len(df)} 条深度快照')
    else:
        print('❌ 未获取到深度数据')

if __name__ == '__main__':
    main()