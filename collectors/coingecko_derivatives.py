"""
CoinGecko Derivatives API
聚合 Binance / Bybit / OKX / Bitget / Gate 等主流交易所的 BTC/ETH 永续数据
API: https://api.coingecko.com/api/v3/derivatives
免费层：30 次/分钟，无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/coingecko_derivatives.csv')
URL = 'https://api.coingecko.com/api/v3/derivatives'

TARGET_MARKETS = [
    'Binance (Futures)',
    'Bybit (Futures)',
    'OKX (Futures)',
    'Bitget (Futures)',
    'Gate (Futures)',
    'HTX (Futures)',
    'MEXC (Futures)',
]

TARGET_INDEX = ['BTC', 'ETH']


def fetch():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    try:
        data = fetch()
        print(f'总条目: {len(data)}')
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    rows = []
    for item in data:
        market = item.get('market', '')
        idx = item.get('index_id', '')
        ctype = item.get('contract_type', '')
        if idx not in TARGET_INDEX:
            continue
        if ctype != 'perpetual':
            continue
        if market not in TARGET_MARKETS:
            continue
        fr_pct = item.get('funding_rate')
        oi = item.get('open_interest') or 0
        vol = item.get('volume_24h') or 0
        rows.append({
            'date': today,
            'market': market,
            'index': idx,
            'symbol': item.get('symbol', ''),
            'price': item.get('price'),
            'funding_rate_pct': fr_pct,
            'funding_rate_annual_pct': (fr_pct * 3 * 365) if fr_pct is not None else None,
            'open_interest_usd': oi,
            'volume_24h_usd': vol,
        })

    if not rows:
        print('❌ 没有匹配的条目')
        sys.exit(1)

    # 每个 market + index 只保留 OI 最大（USDT 本位合约）
    df_new = pd.DataFrame(rows)
    df_new = df_new.sort_values('open_interest_usd', ascending=False)
    df_new = df_new.drop_duplicates(subset=['date', 'market', 'index'], keep='first')

    print(f'去重后 {len(df_new)} 条:')
    for _, r in df_new.iterrows():
        fr_ann = r['funding_rate_annual_pct']
        oi_b = r['open_interest_usd'] / 1e9
        fr_str = f"{fr_ann:+.2f}%" if fr_ann is not None else "N/A"
        print(f"  {r['market']:22s} {r['index']}: FR年化 {fr_str}, OI ${oi_b:.2f}B")

    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'market', 'index'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'market', 'index'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()