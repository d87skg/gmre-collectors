"""
CoinGecko 全市场宏观快照
- 总市值（USD）
- BTC/ETH 市占率
- 活跃币种数
API: https://api.coingecko.com/api/v3/global
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/coingecko_global.csv')
URL = 'https://api.coingecko.com/api/v3/global'


def main():
    try:
        r = requests.get(URL, timeout=30)
        r.raise_for_status()
        data = r.json().get('data', {})
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    mcap_pct = data.get('market_cap_percentage', {})
    total_mcap = data.get('total_market_cap', {}).get('usd')

    rows = [
        {'date': today, 'series': 'TOTAL_MCAP_USD_B',
         'value': total_mcap / 1e9 if total_mcap else None},
        {'date': today, 'series': 'BTC_DOMINANCE',
         'value': mcap_pct.get('btc')},
        {'date': today, 'series': 'ETH_DOMINANCE',
         'value': mcap_pct.get('eth')},
        {'date': today, 'series': 'ACTIVE_CRYPTOS',
         'value': data.get('active_cryptocurrencies')},
    ]
    rows = [r for r in rows if r['value'] is not None]

    print(f'拿到 {len(rows)} 条:')
    for r in rows:
        v = r['value']
        if 'MCAP' in r['series']:
            print(f"  {r['series']}: ${v:,.0f}B")
        elif 'DOMINANCE' in r['series']:
            print(f"  {r['series']}: {v:.2f}%")
        else:
            print(f"  {r['series']}: {v}")

    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'series'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()