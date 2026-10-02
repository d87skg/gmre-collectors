"""
DefiLlama 稳定币总市值
API: https://stablecoins.llama.fi/stablecoincharts/all
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/defillama_stablecoin.csv')
URL = 'https://stablecoins.llama.fi/stablecoincharts/all'


def fetch():
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data:
        ts = item.get('date')
        if not ts:
            continue
        try:
            ts_int = int(ts)
        except (ValueError, TypeError):
            continue
        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
        total = item.get('totalCirculating', {})
        if not isinstance(total, dict):
            continue
        total_usd = total.get('peggedUSD')
        if total_usd is None:
            continue
        rows.append({
            'date': dt.strftime('%Y-%m-%d'),
            'total_usd': float(total_usd),
        })
    return rows


def main():
    try:
        rows = fetch()
        print(f'拿到 {len(rows)} 条')
    except Exception as e:
        print(f'❌ 失败: {e}')
        sys.exit(1)

    if not rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(rows)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values('date')
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(3).to_string())


if __name__ == '__main__':
    main()