"""
OKX 爆仓数据（最近 3 天，实时）
API: https://www.okx.com/api/v5/public/liquidation-orders
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/okx_liquidation.csv')
BASE = 'https://www.okx.com/api/v5/public/liquidation-orders'

# BTC/ETH 的 USDT 永续
ULYS = ['BTC-USDT', 'ETH-USDT']


def fetch(uly):
    params = {
        'instType': 'SWAP',
        'uly': uly,
        'state': 'filled',
        'limit': 100,
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('code') != '0':
        raise RuntimeError(f'API 返回异常: {data}')
    rows = []
    for item in data.get('data', []):
        for d in item.get('details', []):
            ts = int(d['ts']) / 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            rows.append({
                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'uly': uly,
                'pos_side': d['posSide'],   # long / short
                'size': float(d['sz']),     # 合约张数
                'price': float(d['bkPx']),  # 爆仓价
            })
    return rows


def main():
    all_rows = []
    for uly in ULYS:
        try:
            rows = fetch(uly)
            print(f'{uly}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{uly} 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'uly', 'pos_side', 'size', 'price'],
            keep='last'
        )
    else:
        df = df_new

    df = df.sort_values('datetime')
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(6).to_string())


if __name__ == '__main__':
    main()