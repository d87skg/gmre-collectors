"""
IMF SDMX API - 新兴市场外储 + 央行黄金储备
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path('data/imf_reserves.csv')

# IMF SDMX 2.1 端点（无需认证）
BASE = 'https://dataservices.imf.org/REST/SDMX_JSON.svc'

# 国家代码（IMF 用 ISO-2）
COUNTRIES = {
    'IN': 'India',
    'BR': 'Brazil',
    'TR': 'Turkey',
    'ZA': 'South Africa',
    'MX': 'Mexico',
    'ID': 'Indonesia',
}


def fetch_reserves(country_code):
    """外汇储备（含黄金，IFS 数据集）"""
    # IFS: 官方储备资产，单位：USD
    # 维度：FREQ.A(annual), REF_AREA.<country>, INDICATOR.RAFAGOLD_USD
    url = f'{BASE}/Dataflow/IFS/'
    # 用更稳定的端点
    url = (f'https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData/IFS/'
           f'M.{country_code}.RAFA_USD')
    r = requests.get(url, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f'HTTP {r.status_code}: {r.text[:200]}')
    data = r.json()
    try:
        obs = data['CompactData']['DataSet']['Series']['Obs']
        if isinstance(obs, dict):
            obs = [obs]
        rows = []
        for o in obs[-60:]:
            date = o.get('@TIME_PERIOD', '')
            v = o.get('@OBS_VALUE')
            if v and v != '':
                rows.append({
                    'date': date,
                    'series': f'RESERVES_{country_code}',
                    'value': float(v) / 1e9,
                })
        return rows
    except (KeyError, TypeError) as e:
        raise RuntimeError(f'解析失败: {e}')


def main():
    all_rows = []
    for code in COUNTRIES:
        try:
            rows = fetch_reserves(code)
            print(f'{code}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{code} 失败: {str(e)[:100]}')

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