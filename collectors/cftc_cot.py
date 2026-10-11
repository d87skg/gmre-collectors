"""
CFTC COT 金融期货
来源: https://www.cftc.gov/dea/newcot/FinFutWk.txt
输出: data/cftc_cot.csv
"""
import requests
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

URL = 'https://www.cftc.gov/dea/newcot/FinFutWk.txt'
OUT = Path('data/cftc_cot.csv')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
}

TARGETS = {
    'UST 10Y NOTE': 'COT_UST10Y',
    'UST BOND':     'COT_UST30Y',
    'UST 5Y NOTE':  'COT_UST5Y',
    'FED FUNDS':    'COT_FEDFUNDS',
    'SOFR-3M':      'COT_SOFR3M',
    'EURO FX':      'COT_EUR',
    'BITCOIN':      'COT_BTC_CME',
}


def fetch():
    r = requests.get(URL, headers=HEADERS, timeout=30)
    print(f'HTTP {r.status_code}, 长度 {len(r.text)}')
    r.raise_for_status()
    lines = r.text.split('\n')
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) < 12:
            continue
        name = parts[0].strip().strip('"').strip()
        for keyword, series_id in TARGETS.items():
            if name.startswith(keyword + ' -') or name == keyword:
                try:
                    records.append({
                        'date': parts[2].strip(),
                        'series_id': series_id,
                        'market_name': name,
                        'open_interest': int(parts[7]),
                        'nc_long': int(parts[8]),
                        'nc_short': int(parts[9]),
                        'net_noncommercial': int(parts[8]) - int(parts[9]),
                    })
                except Exception as e:
                    print(f'解析失败: {name[:40]} - {e}')
                break
    return records


def main():
    recs = fetch()
    print(f'原始 {len(recs)} 条')
    if not recs:
        print('❌ 无数据')
        sys.exit(1)

    df_new = pd.DataFrame(recs)
    df_new = (df_new.sort_values('open_interest', ascending=False)
                    .drop_duplicates(subset=['series_id'], keep='first'))
    print(f'去重后 {len(df_new)} 条')
    df_new['retrieved_at'] = datetime.utcnow().isoformat()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series_id'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'series_id'])
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')


if __name__ == '__main__':
    main()