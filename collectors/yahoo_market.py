"""
Yahoo Finance 市场数据
- VIX / DXY / GOLD / OIL（原）
- NDX（纳斯达克 100）/ TLT（20Y+ 美债 ETF）（新增）
API: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/yahoo_market.csv')
BASE = 'https://query1.finance.yahoo.com/v8/finance/chart'

SYMBOLS = {
    '^VIX':      'VIX',
    'DX-Y.NYB':  'DXY',
    'GC=F':      'GOLD',
    'CL=F':      'OIL',
    '^NDX':      'NDX',
    'TLT':       'TLT',
}


def fetch(symbol, yahoo_id, days=90):
    url = f'{BASE}/{yahoo_id}'
    params = {'interval': '1d', 'range': f'{days}d'}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/120.0.0.0 Safari/537.36'
    }
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    result = data['chart']['result'][0]
    timestamps = result['timestamp']
    closes = result['indicators']['quote'][0]['close']
    rows = []
    for ts, c in zip(timestamps, closes):
        if c is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            'date': dt.strftime('%Y-%m-%d'),
            'symbol': symbol,
            'value': float(c),
        })
    return rows


def main():
    all_rows = []
    for yahoo_id, symbol in SYMBOLS.items():
        try:
            rows = fetch(symbol, yahoo_id)
            print(f'{symbol}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{symbol} 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'symbol'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'symbol'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(8).to_string())


if __name__ == '__main__':
    main()