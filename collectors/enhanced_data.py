# -*- coding: utf-8 -*-
"""collectors/enhanced_data.py - 补全流动性/风险核心序列（带防卡死保护）"""
import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
import io
import re
import sqlite3
import pandas as pd

from core.database import Database

DB_PATH = os.environ.get('GMRE_DB_PATH', 'data/macro.db')
PROXIES = None

def _append(series_id, obs_ts, value, source, unit=None, frequency='daily'):
    db = Database(DB_PATH)
    try:
        return db.insert_observation(series_id, obs_ts, float(value), source=source, unit=unit, frequency=frequency)
    finally:
        db.conn.close()

FRED_SERIES = {
    'WRESBAL': 'RESERVE_BALANCE', 'SOFR': 'SOFR', 'WLCFLPCL': 'DISCOUNT_WINDOW',
    'WLRRAL': 'REVERSE_REPO_FRED', 'EFFR': 'EFFR', 'IORB': 'IORB',
    'DEXJPUS': 'USD_JPY', 'IRLTLT01JPM156N': 'JP_10Y_YIELD',
    'IR3TIB01JPM156N': 'JP_3M_RATE', 'DEXJPUS_DAILY': 'USD_JPY_ALT',
}

def fetch_fred_csv(sid, local_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    try:
        # 🆕 缩短超时时间，防止卡死
        r = requests.get(url, timeout=10, proxies=PROXIES)
        if r.status_code != 200: 
            print(f"    ⚠️ {sid} 请求失败: HTTP {r.status_code}")
            return 0
        df = pd.read_csv(io.StringIO(r.text))
        df.columns = ['date', 'value']
        df = df[df['value'] != '.']
        count = 0
        for _, row in df.iterrows():
            try:
                _append(local_id, str(row['date']), row['value'], 'fred_csv')
                count += 1
            except Exception: pass
        return count
    except requests.exceptions.Timeout:
        print(f"    ⏱️ {sid} 请求超时 (10s)，跳过")
        return 0
    except Exception as e:
        print(f"    ❌ {sid} 请求异常: {str(e)[:50]}")
        return 0

_TGA_RE = re.compile(r'treasury\s+general\s+account', re.I)
_OPEN_RE = re.compile(r'opening', re.I)
_CLOSE_RE = re.compile(r'clos', re.I)

def parse_tga_records(records):
    dated = {}
    for rec in records or []:
        atype = rec.get('account_type') or ''
        if not _TGA_RE.search(atype): continue
        bal = rec.get('open_today_bal')
        if bal in (None, '', 'null'): continue
        try: val = float(bal)
        except: continue
        rd = rec.get('record_date')
        if not rd: continue
        rank = 2 if _OPEN_RE.search(atype) else (1 if not _CLOSE_RE.search(atype) else 0)
        if rd not in dated or rank > dated[rd][1]: dated[rd] = (val, rank)
    return [(d, v) for d, (v, _r) in sorted(dated.items())]

def fetch_treasury_daily_tga():
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
    params = {'filter': 'record_date:gte:2024-01-01', 'sort': '-record_date', 'page[size]': 1000}
    try:
        r = requests.get(url, params=params, timeout=10, proxies=PROXIES)
        payload = r.json()
    except Exception as e:
        print(f"  ❌ 财政部API失败: {str(e)[:50]}")
        return 0
    records = payload.get('data', [])
    parsed = parse_tga_records(records)
    if not parsed:
        print("  ❌ TGA 零匹配！")
        return 0
    count = 0
    for d, v in parsed:
        try:
            _append('TGA_DAILY', d, v, 'treasury_fiscal_data', unit='million_usd')
            count += 1
        except Exception: pass
    print(f"  ✅ TGA_DAILY: {count} 行 (最新 {parsed[-1][0]})")
    return count

def fetch_nyfed_rrp():
    url = "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json"
    try:
        r = requests.get(url, params={'startDate': '2024-01-01'}, timeout=10, proxies=PROXIES)
        if r.status_code != 200: return 0
        data = r.json()
        ops = data.get('repo', {}).get('operations', [])
        if not ops: return 0
        count = 0
        for op in ops:
            try:
                amt_billion = float(op.get('totalAmtAccepted', 0)) / 1_000_000_000
                _append('RRP_NYFED', op['operationDate'], amt_billion, 'nyfed_official', unit='billion_usd')
                count += 1
            except Exception: pass
        return count
    except Exception as e:
        print(f"  纽约联储API失败: {str(e)[:50]}")
        return 0

if __name__ == "__main__":
    print("=" * 60 + "\n  增强数据采集\n" + "=" * 60)
    
    print("\n[1/3] FRED 补充序列...")
    for fred_id, local_id in FRED_SERIES.items():
        print(f"  🔄 正在拉取 {fred_id} -> {local_id}...")
        n = fetch_fred_csv(fred_id, local_id)
        if n > 0:
            print(f"  ✅ {fred_id:15s} -> {local_id:20s} {n} 条")
        time.sleep(0.2) # 稍微缩短间隔
        
    print("\n[2/3] 财政部每日TGA...")
    fetch_treasury_daily_tga()
    
    print("\n[3/3] 纽约联储官方RRP...")
    fetch_nyfed_rrp()
    
    print("\n🎉 增强数据采集完成！")