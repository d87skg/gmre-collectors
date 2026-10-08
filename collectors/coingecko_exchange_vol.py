"""
CoinGecko 交易所 24h 成交量（BTC 计价）
API: https://api.coingecko.com/api/v3/exchanges
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/coingecko_exchange_vol.csv')
URL = 'https://api.coingecko.com/api/v3/exchanges'

TARGETS = ['binance', 'coinbase', 'okx', 'bybit_spot', 'kraken',
           'upbit', 'gate', 'huobi', 'kucoin', 'bitfinex']


def main():
    params = {'per_page': 100, 'page': 1}
    try:
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    rows = []
    for ex in data:
        eid = ex.get('id', '')
        if eid not in TARGETS:
            continue
        vol_btc = ex.get('trade_volume_24h_btc')
        rows.append({
            'date': today,
            'exchange_id': eid,
            'exchange_name': ex.get('name', ''),
            'volume_24h_btc': vol_btc,
            'trust_score': ex.get('trust_score'),
        })

    print(f'拿到 {len(rows)} 条:')
    for r in rows:
        v = r['volume_24h_btc'] or 0
        print(f"  {r['exchange_name']:15s}: {v:,.0f} BTC")

    if not rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'exchange_id'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'exchange_id'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()