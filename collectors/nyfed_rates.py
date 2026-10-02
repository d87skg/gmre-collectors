"""
NY Fed 利率（SOFR + EFFR）
API: https://markets.newyorkfed.org/api/rates
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/nyfed_rates.csv')
BASE = 'https://markets.newyorkfed.org/api/rates'


def fetch_sofr():
    url = f'{BASE}/secured/sofr/last/100.json'
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data.get('refRates', []):
        rows.append({
            'date': item['effectiveDate'],
            'series': 'SOFR',
            'value': float(item['percentRate']),
        })
    return rows


def fetch_effr():
    url = f'{BASE}/unsecured/effr/last/100.json'
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    rows = []
    for item in data.get('refRates', []):
        rows.append({
            'date': item['effectiveDate'],
            'series': 'EFFR',
            'value': float(item['percentRate']),
        })
    return rows


def main():
    all_rows = []
    for name, fn in [('SOFR', fetch_sofr), ('EFFR', fetch_effr)]:
        try:
            rows = fn()
            print(f'{name}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{name} 失败: {e}')

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
    print(df.tail(4).to_string())


if __name__ == '__main__':
    main()