"""
Bybit 永续合约资金费率 + 未平仓合约量
API: https://api.bybit.com/v5/market
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT_FUNDING = Path('data/bybit_funding.csv')
OUT_OI = Path('data/bybit_oi.csv')
BASE = 'https://api.bybit.com/v5/market'

SYMBOLS = ['BTCUSDT', 'ETHUSDT']


def fetch_funding(symbol, limit=200):
    url = f'{BASE}/funding/history'
    params = {'category': 'linear', 'symbol': symbol, 'limit': limit}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('retCode') != 0:
        raise RuntimeError(f'API 返回异常: {data}')
    rows = []
    for item in data['result']['list']:
        ts = int(item['fundingRateTimestamp']) / 1000
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        rows.append({
            'datetime': dt.strftime('%Y-%m-%d %H:%M'),
            'symbol': symbol,
            'funding_rate': float(item['fundingRate']),
        })
    return rows


def fetch_oi(symbol):
    """用 tickers 端点，时间戳取响应顶层的 time"""
    url = f'{BASE}/tickers'
    params = {'category': 'linear', 'symbol': symbol}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('retCode') != 0:
        raise RuntimeError(f'API 返回异常: {data}')

    ts = int(data['time']) / 1000
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    dt_str = dt.strftime('%Y-%m-%d %H:%M')

    rows = []
    for item in data['result']['list']:
        oi = item.get('openInterest')
        oi_val = item.get('openInterestValue')
        if oi is None:
            continue
        rows.append({
            'datetime': dt_str,
            'symbol': symbol,
            'oi': float(oi),
            'oi_value': float(oi_val) if oi_val else 0,
        })
    return rows


def append_csv(rows, out):
    if not rows:
        return
    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        df_old = pd.read_csv(out)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['datetime', 'symbol'], keep='last'
        )
    else:
        df = df_new
    df = df.sort_values(['datetime', 'symbol'])
    df.to_csv(out, index=False)
    print(f'已保存: {out} ({len(df)} 行)')


def main():
    funding_rows = []
    oi_rows = []
    for sym in SYMBOLS:
        try:
            rows = fetch_funding(sym)
            print(f'Funding {sym}: {len(rows)} 条')
            funding_rows.extend(rows)
        except Exception as e:
            print(f'Funding {sym} 失败: {e}')
        try:
            rows = fetch_oi(sym)
            print(f'OI {sym}: {len(rows)} 条')
            oi_rows.extend(rows)
        except Exception as e:
            print(f'OI {sym} 失败: {e}')

    if not funding_rows and not oi_rows:
        print('❌ 无数据')
        sys.exit(1)

    append_csv(funding_rows, OUT_FUNDING)
    append_csv(oi_rows, OUT_OI)


if __name__ == '__main__':
    main()