"""
Blockchain.com Charts API（无需 key）
获取 BTC 链上基础指标
API: https://api.blockchain.info/charts/{chart}
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/blockchain_com.csv')
BASE = 'https://api.blockchain.info/charts'

# 只保留支持 timespan 的端点（去掉 total-bitcoins / market-cap，它们返回全历史）
CHARTS = [
    'market-price',
    'n-transactions',
    'n-unique-addresses',
    'miners-revenue',
    'transaction-fees-usd',
    'hash-rate',
]


def fetch(chart, timespan='90days'):
    url = f'{BASE}/{chart}'
    params = {'timespan': timespan, 'format': 'json', 'sampled': 'false'}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'values' not in data:
        raise RuntimeError(f'{chart} 返回异常')
    return [(v['x'], v['y']) for v in data['values']]


def main():
    all_series = {}
    for chart in CHARTS:
        try:
            series = fetch(chart)
            all_series[chart] = series
            print(f'{chart}: {len(series)} 点')
        except Exception as e:
            print(f'{chart} 失败: {e}')

    if not all_series:
        print('❌ 无数据')
        sys.exit(1)

    frames = []
    for chart, series in all_series.items():
        df = pd.DataFrame(series, columns=['ts', chart])
        df['date'] = pd.to_datetime(df['ts'], unit='s', utc=True).dt.strftime('%Y-%m-%d')
        # 关键：同一天多条只保留最后一条
        df = df.drop_duplicates(subset=['date'], keep='last')
        df = df[['date', chart]]
        frames.append(df)

    from functools import reduce
    df = reduce(lambda a, b: pd.merge(a, b, on='date', how='outer'), frames)
    df = df.sort_values('date').reset_index(drop=True)
    df['retrieved_at'] = datetime.utcnow().isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df]).drop_duplicates(
            subset=['date'], keep='last'
        ).sort_values('date').reset_index(drop=True)

    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(3).to_string())


if __name__ == '__main__':
    main()