"""
OKX 永续合约资金费率（替代 Binance）
API: https://www.okx.com/api/v5/public/funding-rate-history
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/okx_funding.csv')
BASE = 'https://www.okx.com/api/v5/public/funding-rate-history'

INST_IDS = ['BTC-USDT-SWAP', 'ETH-USDT-SWAP']


def fetch(inst_id, limit=100):
    params = {'instId': inst_id, 'limit': limit}
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('code') != '0':
        raise RuntimeError(f'API 返回异常: {data}')
    rows = []
    for item in data['data']:
        ts = int(item['fundingTime']) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'symbol': inst_id.replace('-USDT-SWAP', ''),
            'funding_rate': float(item['fundingRate']),
        })
    return rows


def main():
    all_rows = []
    for iid in INST_IDS:
        try:
            rows = fetch(iid)
            print(f'{iid}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{iid} 失败: {e}')

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