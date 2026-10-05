"""
Eurostat HICP（欧元区调和 CPI 年率）
API: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/eurostat_hicp.csv')
BASE = 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr'


def fetch(geo='EA', coicop='CP00', start='2024-01'):
    params = {
        'geo': geo,
        'coicop': coicop,
        'sinceTimePeriod': start,
        'format': 'JSON',
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'value' not in data or 'dimension' not in data:
        raise RuntimeError(f'API 返回异常')
    # time 维度的索引 → 日期标签
    time_idx = data['dimension']['time']['category']['index']
    # value 里 key 是字符串索引
    rows = []
    for k, v in data['value'].items():
        if v is None:
            continue
        try:
            pos = int(k)
        except (ValueError, TypeError):
            continue
        # 找对应日期
        date_label = None
        for label, idx in time_idx.items():
            if idx == pos:
                date_label = label
                break
        if date_label is None:
            continue
        rows.append({
            'date': date_label,
            'series': 'EA_HICP',
            'value': float(v),
        })
    return rows


def main():
    try:
        rows = fetch()
        print(f'HICP: {len(rows)} 条')
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

    df = df.sort_values('date')
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(5).to_string())


if __name__ == '__main__':
    main()