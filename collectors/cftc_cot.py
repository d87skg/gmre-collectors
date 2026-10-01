"""
CFTC COT 周度持仓报告
输出: data/cftc_cot.csv
"""
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path

URL = 'https://www.cftc.gov/dea/newcot/FinFutWk.txt'
OUT = Path('data/cftc_cot.csv')

TARGETS = {
    'UST 10Y NOTE': 'COT_UST10Y',
    'UST BOND': 'COT_UST30Y',
    'USD INDEX': 'COT_DXY',
    'GOLD': 'COT_GOLD',
}

def fetch():
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    lines = r.text.split('\n')
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) < 10:
            continue
        name = parts[0].strip()
        if name in TARGETS:
            try:
                date_str = parts[2].strip()
                nc_long = int(parts[8])
                nc_short = int(parts[9])
                net = nc_long - nc_short
                records.append({
                    'date': date_str,
                    'series_id': TARGETS[name],
                    'net_noncommercial': net,
                })
            except Exception:
                continue
    return records

def main():
    recs = fetch()
    print(f'拿到 {len(recs)} 条')
    if not recs:
        return

    df_new = pd.DataFrame(recs)
    df_new['retrieved_at'] = datetime.utcnow().isoformat()

    # 合并历史
    if OUT.exists():
        df_old = pd.read_csv(OUT)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series_id'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values('date')
    OUT.parent.mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f'已保存: {OUT} ({len(df)} 行)')

if __name__ == '__main__':
    main()