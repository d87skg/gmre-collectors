"""
Treasury General Account (TGA) 余额
API: https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance
无需 key
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path('data/treasury_tga.csv')
BASE = 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance'


def fetch(days=90):
    start = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')
    params = {
        'filter': f'record_date:gte:{start},account_type:eq:Treasury General Account (TGA) Closing Balance',
        'sort': '-record_date',
        'page[size]': 200,
    }
    r = requests.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    if 'data' not in data:
        raise RuntimeError(f'API 返回异常: {data}')
    rows = []
    for item in data['data']:
        bal = item.get('close_today_bal')
        if bal is None:
            continue
        try:
            value = float(bal) / 1e6  # 百万 → 十亿
        except (ValueError, TypeError):
            continue
        rows.append({
            'date': item['record_date'],
            'series': 'TGA',
            'value': value,
        })
    return rows


def main():
    try:
        rows = fetch()
        print(f'TGA: {len(rows)} 条')
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