"""
World Bank API - 新兴市场外储
指标 FI.RES.TOTL.CD = Total reserves (includes gold, current US$)
WorldBank 用 ISO-3 国家代码
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/worldbank_reserves.csv')

# ISO-3 代码
COUNTRIES = {
    'IND': 'India',
    'BRA': 'Brazil',
    'TUR': 'Turkey',
    'ZAF': 'South Africa',
    'MEX': 'Mexico',
    'IDN': 'Indonesia',
}

INDICATOR = 'FI.RES.TOTL.CD'


def fetch_all():
    """一次性拉所有国家"""
    codes = ';'.join(COUNTRIES.keys())
    url = f'https://api.worldbank.org/v2/country/{codes}/indicator/{INDICATOR}'
    params = {
        'format': 'json',
        'per_page': 500,
        'mrv': 5,  # 最近 5 年
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}')
    data = r.json()
    if len(data) < 2 or not data[1]:
        return []
    rows = []
    for item in data[1]:
        iso3 = item.get('countryiso3code')
        if iso3 not in COUNTRIES:
            continue
        v = item.get('value')
        d = item.get('date')
        if v is None or d is None:
            continue
        rows.append({
            'date': d,
            'series': f'RESERVES_{iso3}',
            'value': float(v) / 1e9,  # $B
        })
    return rows


def main():
    try:
        rows = fetch_all()
        print(f'共 {len(rows)} 条')
        for code in COUNTRIES:
            n = len([r for r in rows if r['series'] == f'RESERVES_{code}'])
            print(f'  {code}: {n} 条')
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
            subset=['date', 'series'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'series'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()