"""
BGeometrics 链上估值指标
- MVRV Z-Score
- SOPR
- NVT
- NUPL
环境变量: BGEOMETRICS_API_KEY（免费层可能无需 key）
"""
import os
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/bgeometrics.csv')
API_KEY = os.environ.get('BGEOMETRICS_API_KEY', '')
BASE = 'https://bitcoin-data.com/api/v1'

METRICS = {
    'mvrv-zscore': 'MVRV_ZSCORE',
    'sopr': 'SOPR',
    'nvt': 'NVT',
    'nupl': 'NUPL',
}


def fetch(metric):
    url = f'{BASE}/{metric}'
    headers = {}
    if API_KEY:
        headers['Authorization'] = f'Bearer {API_KEY}'
    r = requests.get(url, headers=headers, params={'limit': 180}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    rows = []
    if isinstance(data, list):
        for item in data:
            d = item.get('d', item.get('date', ''))[:10]
            v = item.get('v', item.get('value'))
            if d and v is not None:
                rows.append({
                    'date': d,
                    'series': METRICS.get(metric, metric),
                    'value': float(v),
                })
    return rows


def main():
    all_rows = []
    for metric, sid in METRICS.items():
        try:
            rows = fetch(metric)
            print(f'{sid}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{sid} 失败: {e}')

    if not all_rows:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(all_rows)
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
    print(df.tail(8).to_string())


if __name__ == '__main__':
    main()