"""
CoinGecko 全市场宏观快照
- 总市值（USD，以 B 为单位）
- BTC 市占率
- ETH 市占率
- 活跃币种数

API: https://api.coingecko.com/api/v3/global
无需 key
输出: data/coingecko_global.csv

注：TOTAL_VOLUME 因 CoinGecko 免费层数据不可靠，已移除。
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/coingecko_global.csv')
URL = 'https://api.coingecko.com/api/v3/global'


def fetch():
    """拉取 CoinGecko 全市场数据"""
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    return r.json().get('data', {})


def build_rows(data):
    """组装要保存的行"""
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    mcap_pct = data.get('market_cap_percentage', {})
    total_mcap = data.get('total_market_cap', {}).get('usd')

    rows = [
        {
            'date': today,
            'series': 'TOTAL_MCAP_USD_B',
            'value': total_mcap / 1e9 if total_mcap else None,
        },
        {
            'date': today,
            'series': 'BTC_DOMINANCE',
            'value': mcap_pct.get('btc'),
        },
        {
            'date': today,
            'series': 'ETH_DOMINANCE',
            'value': mcap_pct.get('eth'),
        },
        {
            'date': today,
            'series': 'ACTIVE_CRYPTOS',
            'value': data.get('active_cryptocurrencies'),
        },
    ]
    # 过滤掉 None
    rows = [r for r in rows if r['value'] is not None]
    return rows


def save(rows):
    """追加保存到 CSV（按 date + series 去重）"""
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
    return len(df)


def main():
    try:
        data = fetch()
    except Exception as e:
        print(f'❌ 拉取失败: {e}')
        sys.exit(1)

    rows = build_rows(data)
    if not rows:
        print('❌ 无数据')
        sys.exit(1)

    print(f'拿到 {len(rows)} 条:')
    for r in rows:
        sid = r['series']
        v = r['value']
        if 'MCAP' in sid:
            print(f'  {sid}: ${v:,.1f}B')
        elif 'DOMINANCE' in sid:
            print(f'  {sid}: {v:.2f}%')
        else:
            print(f'  {sid}: {v}')

    total = save(rows)
    print(f'已保存: {OUT} ({total} 行)')


if __name__ == '__main__':
    main()