"""
BOJ 日本央行利率（无担保隔夜拆借利率 + 政策利率）
API: https://www.stat-search.boj.or.jp/api/v1
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/boj_rates.csv')
BASE = 'https://www.stat-search.boj.or.jp/api/v1/getDataCode'

SERIES = {
    'STRDCLUCON': 'BOJ_CALL_RATE',     # 无担保隔夜拆借利率
}


def fetch(code):
    params = {
        'format': 'json',
        'lang': 'en',
        'db': 'FM01',
        'code': code,
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if data.get('STATUS') != 200:
        raise RuntimeError(f'{code} 返回异常: {data.get("MESSAGE")}')
    resultset = data.get('RESULTSET', [])
    if not resultset:
        return []
    item = resultset[0]
    values_dict = item.get('VALUES', {})
    dates = values_dict.get('SURVEY_DATES', [])
    vals = values_dict.get('VALUES', [])
    rows = []
    for d, v in zip(dates, vals):
        if v is None:
            continue
        # d 格式: 20240101 (int 或 str)
        d_str = str(d)
        if len(d_str) >= 8:
            date_fmt = f'{d_str[:4]}-{d_str[4:6]}-{d_str[6:8]}'
        elif len(d_str) == 6:
            date_fmt = f'{d_str[:4]}-{d_str[4:6]}'
        else:
            date_fmt = d_str
        rows.append({
            'date': date_fmt,
            'series': SERIES.get(code, code),
            'value': float(v),
        })
    return rows


def main():
    all_rows = []
    for code, sid in SERIES.items():
        try:
            rows = fetch(code)
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

    df = df.sort_values('date')
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')
    print(df.tail(5).to_string())


if __name__ == '__main__':
    main()