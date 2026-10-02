"""
Binance 永续合约资金费率
API: https://fapi.binance.com/fapi/v1/fundingRate
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/binance_funding.csv')
BASE = 'https://fapi.binance.com/fapi/v1'

SYMBOLS = ['BTCUSDT', 'ETHUSDT']


def fetch(symbol, limit=100):
    url = f'{BASE}/fundingRate'
    params = {'symbol': symbol, 'limit': limit}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data:
        ts = int(item['fundingTime']) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'symbol': symbol,
            'funding_rate': float(item['fundingRate']),
        })
    return rows


def main():
    all_rows = []
    for sym in SYMBOLS:
        try:
            rows = fetch(sym)
            print(f'{sym}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{sym} 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'symbol'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['datetime', 'symbol'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(4).to_string())


if __name__ == '__main__':
    main()