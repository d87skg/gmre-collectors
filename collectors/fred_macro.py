"""
FRED 宏观指标
- WRESBAL: 准备金余额
- CPF3M: 3个月商业票据利率
- TB3MS: 3个月国债利率
- THREEFYTP10: 10年期 ACM 期限溢价
- BAMLH0A0HYM2: 高收益债 OAS（信用压力）
- BAMLC0A0CM: 投资级 OAS
- RIFSPPNA2P2D60NB: 60天 AA 非金融 CP 利率（CD 代理）
- DGS2/DGS10/DGS30: 2Y/10Y/30Y 国债收益率
- DRCRELEXFACBS: 商业地产贷款拖欠率（CMBS 代理）
环境变量: FRED_API_KEY
"""
import os
import time
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path('data/fred_macro.csv')
BASE = 'https://api.stlouisfed.org/fred/series/observations'
API_KEY = os.environ.get('FRED_API_KEY')

SERIES = [
    'WRESBAL',
    'CPF3M',
    'TB3MS',
    'THREEFYTP10',
    'BAMLH0A0HYM2',
    'BAMLC0A0CM',
    'RIFSPPNA2P2D60NB',
    'DGS2',
    'DGS10',
    'DGS30',
    'DRCRELEXFACBS',
]


def fetch(series_id, days=180, retries=3):
    start = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {
        'series_id': series_id,
        'api_key': API_KEY,
        'file_type': 'json',
        'observation_start': start,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params=params, timeout=30)
            if r.status_code == 500:
                print(f'{series_id} 500 重试 {attempt+1}/{retries}')
                time.sleep(3)
                continue
            r.raise_for_status()
            data = r.json()
            if 'observations' not in data:
                raise RuntimeError(f'{series_id} 返回异常: {data}')
            rows = []
            for item in data['observations']:
                if item['value'] == '.':
                    continue
                rows.append({
                    'date': item['date'],
                    'series': series_id,
                    'value': float(item['value']),
                })
            return rows
        except Exception as e:
            last_err = e
            time.sleep(3)
    raise last_err


def main():
    if not API_KEY:
        print('❌ 缺 FRED_API_KEY')
        sys.exit(1)

    all_rows = []
    for sid in SERIES:
        try:
            rows = fetch(sid)
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