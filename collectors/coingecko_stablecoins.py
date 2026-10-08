"""
CoinGecko 稳定币细分（逐个币种供应量）
API: https://api.coingecko.com/api/v3/coins/markets?category=stablecoins
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/coingecko_stablecoins.csv')
URL = 'https://api.coingecko.com/api/v3/coins/markets'

TARGETS = ['tether', 'usd-coin', 'dai', 'first-digital-usd', 'ethena-usde']


def main():
    params = {
        'vs_currency': 'usd',
        'category': 'stablecoins',
        'order': 'market_cap_desc',
        'per_page': 50,
        'page': 1,
    }
    try:
        r = requests.get(URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    rows = []
    for coin in data:
        cid = coin.get('id', '')
        if cid not in TARGETS:
            continue
        rows.append({
            'date': today,
            'coin_id': cid,
            'symbol': (coin.get('symbol') or '').upper(),
            'market_cap_usd': coin.get('market_cap'),
            'circulating_supply': coin.get('circulating_supply'),
            'total_supply': coin.get('total_supply'),
        })

    print(f'拿到 {len(rows)} 条:')
    for r in rows:
        mc = r['market_cap_usd'] / 1e9 if r['market_cap_usd'] else 0
        print(f"  {r['symbol']:8s} ${mc:.2f}B")

    if not rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'coin_id'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'coin_id'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()