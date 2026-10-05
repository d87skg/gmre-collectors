"""
BIS 央行政策利率（US / 欧元区 / 日本 / 英国 / 中国）
API: https://stats.bis.org/api/v1/data/WS_CBPOL/M.{area}
无需 key
"""
import io
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/bis_cbpol.csv')
BASE = 'https://stats.bis.org/api/v1/data/WS_CBPOL'

AREAS = {
    'US': 'CB_US',
    'XM': 'CB_EZ',   # 欧元区
    'JP': 'CB_JP',
    'GB': 'CB_GB',
    'CN': 'CB_CN',
}


def fetch(area_code, series_id):
    url = f'{BASE}/M.{area_code}'
    params = {'lastNObservations': 24, 'format': 'csv'}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    if 'TIME_PERIOD' not in df.columns or 'OBS_VALUE' not in df.columns:
        raise RuntimeError(f'{series_id} 字段缺失: {df.columns.tolist()[:10]}')
    rows = []
    for _, row in df.iterrows():
        if pd.isna(row['OBS_VALUE']):
            continue
        rows.append({
            'date': str(row['TIME_PERIOD']),
            'series': series_id,
            'value': float(row['OBS_VALUE']),
        })
    return rows


def main():
    all_rows = []
    for area_code, series_id in AREAS.items():
        try:
            rows = fetch(area_code, series_id)
            print(f'{series_id}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{series_id} 失败: {e}')

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