"""
AKShare 中国宏观数据
- 中国 10Y/2Y 国债收益率
- LPR（1Y/5Y）
- CPI / PPI
- M1 / M2
- 社融
- PMI
- 北向资金
- 70 城房价
"""
import akshare as ak
import pandas as pd
import sys
from datetime import datetime
from pathlib import Path

OUT = Path('data/akshare_china.csv')


def fetch_bond_yield():
    """中美国债收益率"""
    try:
        df = ak.bond_zh_us_rate()
        df = df[['日期', '中国国债收益率10年', '中国国债收益率2年']].dropna()
        df.columns = ['date', 'CN10Y', 'CN2Y']
        rows = []
        for _, r in df.tail(180).iterrows():
            for col in ['CN10Y', 'CN2Y']:
                if pd.notna(r[col]):
                    rows.append({
                        'date': str(r['date']),
                        'series': col,
                        'value': float(r[col]),
                    })
        return rows
    except Exception as e:
        print(f'国债失败: {e}')
        return []


def fetch_lpr():
    """LPR 利率"""
    try:
        df = ak.macro_china_lpr()
        rows = []
        for _, r in df.tail(60).iterrows():
            date = str(r.get('TRADE_DATE', r.get('日期', '')))[:10]
            for col, sid in [('LPR1Y', 'CN_LPR1Y'), ('LPR5Y', 'CN_LPR5Y')]:
                v = r.get(col) or r.get(col.replace('LPR', 'LPR_'))
                if v is not None and pd.notna(v):
                    rows.append({'date': date, 'series': sid, 'value': float(v)})
        return rows
    except Exception as e:
        print(f'LPR 失败: {e}')
        return []


def fetch_cpi_ppi():
    """CPI / PPI 年率"""
    rows = []
    try:
        df = ak.macro_china_cpi_yearly()
        for _, r in df.tail(60).iterrows():
            date = str(r.get('日期', r.get('date', '')))[:10]
            v = r.get('今值')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_CPI', 'value': float(v)})
    except Exception as e:
        print(f'CPI 失败: {e}')
    try:
        df = ak.macro_china_ppi_yearly()
        for _, r in df.tail(60).iterrows():
            date = str(r.get('日期', r.get('date', '')))[:10]
            v = r.get('今值')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_PPI', 'value': float(v)})
    except Exception as e:
        print(f'PPI 失败: {e}')
    return rows


def fetch_m2():
    """M2 年率"""
    try:
        df = ak.macro_china_m2_yearly()
        rows = []
        for _, r in df.tail(60).iterrows():
            date = str(r.get('日期', r.get('date', '')))[:10]
            v = r.get('今值')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_M2', 'value': float(v)})
        return rows
    except Exception as e:
        print(f'M2 失败: {e}')
        return []


def fetch_pmi():
    """PMI"""
    try:
        df = ak.macro_china_pmi_yearly()
        rows = []
        for _, r in df.tail(60).iterrows():
            date = str(r.get('日期', r.get('date', '')))[:10]
            v = r.get('今值')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_PMI', 'value': float(v)})
        return rows
    except Exception as e:
        print(f'PMI 失败: {e}')
        return []


def fetch_social_financing():
    """社融"""
    try:
        df = ak.macro_china_shrzgm()
        rows = []
        for _, r in df.tail(60).iterrows():
            date = str(r.get('月份', r.get('日期', '')))[:7]
            v = r.get('社会融资规模增量')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_TSF', 'value': float(v)})
        return rows
    except Exception as e:
        print(f'社融失败: {e}')
        return []


def fetch_northbound():
    """北向资金"""
    try:
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        rows = []
        for _, r in df.tail(180).iterrows():
            date = str(r.get('date', r.get('日期', '')))[:10]
            v = r.get('value', r.get('当日成交净买额'))
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_NORTHBOUND', 'value': float(v)})
        return rows
    except Exception as e:
        print(f'北向失败: {e}')
        return []


def fetch_house_price():
    """70 城房价"""
    try:
        df = ak.macro_china_new_house_price()
        rows = []
        for _, r in df.tail(60).iterrows():
            date = str(r.get('日期', r.get('date', '')))[:10]
            v = r.get('今值')
            if v is not None and pd.notna(v):
                rows.append({'date': date, 'series': 'CN_HOUSE_PRICE', 'value': float(v)})
        return rows
    except Exception as e:
        print(f'房价失败: {e}')
        return []


def main():
    all_rows = []
    for name, fn in [
        ('国债', fetch_bond_yield),
        ('LPR', fetch_lpr),
        ('CPI/PPI', fetch_cpi_ppi),
        ('M2', fetch_m2),
        ('PMI', fetch_pmi),
        ('社融', fetch_social_financing),
        ('北向', fetch_northbound),
        ('房价', fetch_house_price),
    ]:
        try:
            rows = fn()
            print(f'{name}: {len(rows)} 条')
            all_rows.extend(rows)
        except Exception as e:
            print(f'{name} 失败: {e}')

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