"""
Alternative.me Crypto Fear & Greed Index
API: https://api.alternative.me/fng/
无需 key，完全免费
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('data/fear_greed.csv')
URL = 'https://api.alternative.me/fng/'


def fetch(limit=365):
    params = {'limit': limit, 'format': 'json'}
    r = requests.get(URL, params=params, timeout=30)
    print(f'HTTP {r.status_code}')
    r.raise_for_status()
    data = r.json()
    if 'data' not in data:
        raise RuntimeError(f'API 返回异常: {data}')

    rows = []
    for item in data['data']:
        ts = int(item['timestamp'])
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
        rows.append({
            'date': date,
            'value': int(item['value']),
            'classification': item['value_classification'],
        })
    return rows


def main():
    try:
        rows = fetch()
        print(f'拿到 {len(rows)} 条')
    except Exception as e:
        print(f'❌ 失败: {e}')
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
    print(df.tail(5).to_string())


if __name__ == '__main__':
    main()