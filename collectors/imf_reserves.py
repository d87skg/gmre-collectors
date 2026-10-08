"""
IMF SDMX API - 新兴市场外储 + 全球央行黄金储备
API: https://api.imf.org/external/sdmx/3.0
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path('data/imf_reserves.csv')
BASE = 'https://api.imf.org/external/sdmx/3.0'

COUNTRIES = {
    'IN': 'India',
    'BR': 'Brazil',
    'TR': 'Turkey',
    'ZA': 'South Africa',
    'MX': 'Mexico',
}


def fetch_reserves(country_code):
    """外汇储备（不含黄金）"""
    url = f'{BASE}/data/IFS/M.{country_code}.RAFA_USD'
    params = {
        'startPeriod': (datetime.utcnow() - timedelta(days=730)).strftime('%Y-%m'),
        'format': 'jsondata',
    }
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    rows = []
    try:
        series = data['data']['dataSets'][0]['series']
        for key, s in series.items():
            for obs_key, obs in s['observations'].items():
                v = obs[0]
                if v is None:
                    continue
                # 时间从 dimension 取
                time_dim = data['data']['structure']['dimensions']['observation'][0]
                d = time_dim['values'][int(obs_key)]['id']
                rows.append({
                    'date': d,
                    'series': f'RESERVES_{country_code}',
                    'value': float(v),
                })
    except (KeyError, IndexError) as e:
        raise RuntimeError(f'解析失败: {e}')
    return rows


def main():
    all_rows = []
    for code in COUNTRIES:
        try:
            rows = fetch_reserves(code)
            print(f'{code} 外储: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{code} 失败: {e}')

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
    print(df.tail(10).to_string())


if __name__ == '__main__':
    main()