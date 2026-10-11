"""
World Bank API - 新兴市场外储
端点: https://api.worldbank.org/v2/country/{codes}/indicator/FI.RES.TOTL.CD
指标 FI.RES.TOTL.CD = Total reserves (includes gold, current US$)
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/worldbank_reserves.csv')

COUNTRIES = {
    'IN': 'India',
    'BR': 'Brazil',
    'TR': 'Turkey',
    'ZA': 'South Africa',
    'MX': 'Mexico',
    'ID': 'Indonesia',
}

INDICATOR = 'FI.RES.TOTL.CD'


def fetch(country_code):
    codes = ';'.join(COUNTRIES.keys())
    url = f'https://api.worldbank.org/v2/country/{codes}/indicator/{INDICATOR}'
    params = {
        'format': 'json',
        'per_page': 500,
        'mrv': 12,
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    if len(data) < 2 or not data[1]:
        return []
    rows = []
    for item in data[1]:
        if item.get('countryiso3code') != country_code:
            continue
        v = item.get('value')
        d = item.get('date')
        if v is None or d is None:
            continue
        rows.append({
            'date': d,
            'series': f'RESERVES_{country_code}',
            'value': float(v) / 1e9,
        })
    return rows


def main():
    all_rows = []
    for code in COUNTRIES:
        try:
            rows = fetch(code)
            print(f'{code}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{code} 失败: {str(e)[:120]}')

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


if __name__ == '__main__':
    main()