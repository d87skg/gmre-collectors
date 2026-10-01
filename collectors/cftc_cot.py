"""
CFTC COT 周度持仓报告
来源: https://www.cftc.gov/dea/newcot/FinFutWk.txt
输出: data/cftc_cot.csv

字段位置（短格式，逗号分隔）：
  [0] Market name (带引号)
  [2] Report date (YYYY-MM-DD)
  [7] Open Interest
  [8] NonComm Long
  [9] NonComm Short
  [10] NonComm Spread
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
}

# 关键词 -> series_id（用 in 匹配，容忍后缀）
TARGETS = {
    'UST 10Y NOTE': 'COT_UST10Y',
    'UST BOND':     'COT_UST30Y',
    'UST 5Y NOTE':  'COT_UST5Y',
    'FED FUNDS':    'COT_FEDFUNDS',
    'SOFR-3M':      'COT_SOFR3M',
    'EURO FX':      'COT_EUR',
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
        # 关键修复：去引号
        name = parts[0].strip().strip('"').strip()
        for keyword, series_id in TARGETS.items():
            if keyword in name:
                try:
                    date_str = parts[2].strip()
                    oi = int(parts[7])
                    nc_long = int(parts[8])
                    nc_short = int(parts[9])
                    net = nc_long - nc_short
                    records.append({
                        'date': date_str,
                        'series_id': series_id,
                        'market_name': name,
                        'open_interest': oi,
                        'nc_long': nc_long,
                        'nc_short': nc_short,
                        'net_noncommercial': net,
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

    # 去重：同 series_id 只保留 open_interest 最大的（主合约）
    df_new = (df_new.sort_values('open_interest', ascending=False)
                    .drop_duplicates(subset=['series_id'], keep='first'))
    print(f'去重后 {len(df_new)} 条')
    for _, row in df_new.iterrows():
        print(f"  {row['series_id']}: {row['market_name'][:40]} (OI={row['open_interest']})")

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