"""
CFTC COT via Socrata API（替代官网，官网封云 IP）
数据集: 6dca-aqww（Legacy Futures Only）
无需 key
输出: data/cftc_cot.csv（金融期货）+ data/cftc_fx.csv（外汇）
"""
import requests
import pandas as pd
import sys
from datetime import datetime, timedelta
from pathlib import Path

URL = 'https://publicreporting.cftc.gov/resource/6dca-aqww.json'
OUT_COT = Path('data/cftc_cot.csv')
OUT_FX = Path('data/cftc_fx.csv')

# 金融期货（含 CME BTC）
COT_TARGETS = {
    'UST 10Y NOTE': 'COT_UST10Y',
    'UST BOND':     'COT_UST30Y',
    'UST 5Y NOTE':  'COT_UST5Y',
    'FED FUNDS':    'COT_FEDFUNDS',
    'SOFR-3M':      'COT_SOFR3M',
    'EURO FX':      'COT_EUR',
    'BITCOIN':      'COT_BTC_CME',
}

# 外汇
FX_TARGETS = {
    'JAPANESE YEN':   'COT_JPY',
    'EURO FX':        'COT_EUR',
    'BRITISH POUND':  'COT_GBP',
    'SWISS FRANC':    'COT_CHF',
}


def fetch_all():
    """一次拉所有目标合约最近 8 周"""
    start = (datetime.utcnow() - timedelta(days=60)).strftime('%Y-%m-%d')
    all_names = list(set(list(COT_TARGETS.keys()) + list(FX_TARGETS.keys())))
    names_quoted = ','.join(f"'{n}'" for n in all_names)
    params = {
        '$limit': 5000,
        '$where': f"contract_market_name in ({names_quoted}) AND report_date_as_yyyy_mm_dd > '{start}'",
        '$order': 'report_date_as_yyyy_mm_dd DESC',
    }
    r = requests.get(URL, params=params, timeout=60)
    print(f'HTTP {r.status_code}, 拿到 {len(r.text)} 字节')
    r.raise_for_status()
    return r.json()


def to_int(v):
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def build_rows(data, targets):
    """根据 targets 映射，生成行"""
    rows = []
    for item in data:
        name = item.get('contract_market_name', '').strip()
        if name not in targets:
            continue
        date_str = item.get('report_date_as_yyyy_mm_dd', '')[:10]
        if not date_str:
            continue
        nc_long = to_int(item.get('noncomm_positions_long_all'))
        nc_short = to_int(item.get('noncomm_positions_short_all'))
        rows.append({
            'date': date_str,
            'series_id': targets[name],
            'market_name': name,
            'open_interest': to_int(item.get('open_interest_all')),
            'nc_long': nc_long,
            'nc_short': nc_short,
            'net_noncommercial': nc_long - nc_short,
        })
    return rows


def save(rows, out_path):
    if not rows:
        print(f'⚠️ {out_path.name} 无数据')
        return
    df_new = pd.DataFrame(rows)
    # 去重：同 series_id + date 只保留一行
        # 同 series_id + date 只保留 OI 最大的（主合约）
    df_new = (df_new.sort_values('open_interest', ascending=False)
                    .drop_duplicates(subset=['date', 'series_id'], keep='first'))
    df_new['retrieved_at'] = datetime.utcnow().isoformat()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        df_old = pd.read_csv(out_path)
        df = pd.concat([df_old, df_new]).drop_duplicates(
            subset=['date', 'series_id'], keep='last'
        )
    else:
        df = df_new

    df = df.sort_values(['date', 'series_id'])
    df.to_csv(out_path, index=False)
    print(f'已保存: {out_path} ({len(df)} 行)')


def main():
    try:
        data = fetch_all()
    except Exception as e:
        print(f'❌ Socrata 失败: {e}')
        sys.exit(1)

    if not data:
        print('❌ 无数据')
        sys.exit(1)

    cot_rows = build_rows(data, COT_TARGETS)
    fx_rows = build_rows(data, FX_TARGETS)

    print(f'金融期货: {len(cot_rows)} 条')
    for r in cot_rows[:8]:
        print(f"  {r['date']} {r['series_id']}: {r['net_noncommercial']:+,}")

    print(f'外汇: {len(fx_rows)} 条')
    for r in fx_rows[:8]:
        print(f"  {r['date']} {r['series_id']}: {r['net_noncommercial']:+,}")

    save(cot_rows, OUT_COT)
    save(fx_rows, OUT_FX)


if __name__ == '__main__':
    main()