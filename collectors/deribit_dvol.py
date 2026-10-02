"""
Deribit DVOL（BTC/ETH 隐含波动率指数）
API: https://docs.deribit.com/#public-get_volatility_index_data
输出: data/deribit_dvol.csv
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path('data/deribit_dvol.csv')
BASE = 'https://www.deribit.com/api/v2/public/get_volatility_index_data'


def fetch_dvol(currency='BTC', days=90):
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)
    params = {
        'currency': currency,
        'start_timestamp': start_ms,
        'end_timestamp': end_ms,
        'resolution': '1D',
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'result' not in data or 'data' not in data['result']:
        raise RuntimeError(f'API 返回异常: {data}')

    rows = []
    for candle in data['result']['data']:
        ts, o, h, l, c = candle
        date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append({
            'date': date,
            'currency': currency,
            'open': o,
            'high': h,
            'low': l,
            'close': c,
        })
    return rows


def main():
    all_rows = []
    for ccy in ['BTC', 'ETH']:
        try:
            rows = fetch_dvol(ccy)
            print(f'{ccy} DVOL: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{ccy} 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'currency'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'currency'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(6))


if __name__ == '__main__':
    main()