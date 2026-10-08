"""
CoinGlass v4 全网聚合数据
- 全网 OI
- 全网爆仓
环境变量: COINGLASS_API_KEY
"""
import os
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/coinglass_aggregate.csv')
API_KEY = os.environ.get('COINGLASS_API_KEY')
BASE = 'https://open-api-v4.coinglass.com'


def fetch(endpoint, params=None):
    headers = {
        'accept': 'application/json',
        'CG-API-KEY': API_KEY,
    }
    url = f'{BASE}/{endpoint}'
    r = requests.get(url, headers=headers, params=params or {}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    return r.json()


def main():
    if not API_KEY:
        print('❌ 缺 COINGLASS_API_KEY')
        sys.exit(1)

    all_rows = []

    # 全网 OI 历史
    try:
        data = fetch('api/futures/open-interest/history',
                     {'symbol': 'BTC', 'interval': '1d', 'limit': 90})
        items = data.get('data', [])
        for item in items:
            d = datetime.fromtimestamp(item['time'] / 1000).strftime('%Y-%m-%d')
            v = item.get('openInterest')
            if v is not None:
                all_rows.append({
                    'date': d,
                    'series': 'BTC_OI_ALL',
                    'value': float(v),
                })
        print(f'全网 OI: {len(items)} 条')
    except Exception as e:
        print(f'OI 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values('date')
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(5).to_string())


if __name__ == '__main__':
    main()