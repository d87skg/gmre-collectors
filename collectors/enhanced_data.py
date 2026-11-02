"""collectors/enhanced_data.py - 补全流动性/风险核心序列"""
import requests
import sqlite3
import io
import time
import pandas as pd

DB_PATH = 'data/macro.db'
PROXIES = None
# PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

# ============ A. FRED 补充序列 ============
FRED_SERIES = {
    # 银行/流动性
    'WRESBAL':       'RESERVE_BALANCE',   # 银行准备金（周频）
    'SOFR':          'SOFR',              # 担保隔夜融资利率
    'WLCFLPCL':      'DISCOUNT_WINDOW',   # 贴现窗口一级信贷
    'WLRRAL':        'REVERSE_REPO_FRED', # FRED口径逆回购
    'EFFR':          'EFFR',              # 有效联邦基金利率
    'IORB':          'IORB',              # 准备金余额利率
    # ===== 日元套利监测（核心新增）=====
    'DEXJPUS':       'USD_JPY',           # 美元兑日元汇率（日频）
    'IRLTLT01JPM156N': 'JP_10Y_YIELD',    # 日本10年期国债收益率（月频）
    'IR3TIB01JPM156N': 'JP_3M_RATE',      # 日本3个月银行间利率（月频）
    'DEXJPUS_DAILY': 'USD_JPY_ALT',       # 备用日元序列
}

def fetch_fred_csv(sid, local_id):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    r = requests.get(url, timeout=30, proxies=PROXIES)
    if r.status_code != 200:
        return 0
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ['date', 'value']
    df = df[df['value'] != '.']
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    count = 0
    for _, row in df.iterrows():
        try:
            c.execute(
                """INSERT OR REPLACE INTO observations 
                (series_id, timestamp, value, source, retrieved_at) 
                VALUES (?, ?, ?, ?, datetime('now'))""",
                (local_id, str(row['date']), float(row['value']), 'fred_csv')
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count

# ============ B. 财政部每日TGA（Fiscal Data API，无Key） ============
def fetch_treasury_daily_tga():
    """财政部DTS每日经营现金余额"""
    url = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
    params = {
        'filter': 'record_date:gte:2024-01-01',
        'sort': '-record_date',
        'page[size]': 1000
    }
    try:
        r = requests.get(url, params=params, timeout=30, proxies=PROXIES)
        data = r.json()
        records = data.get('data', [])
        if not records:
            return 0
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        count = 0
        for rec in records:
            # 关键修复：用 in 匹配真实字段名
            atype = rec.get('account_type', '')
            if 'Treasury General Account (TGA) Opening Balance' in atype:
                try:
                    # open_today_bal 单位已是百万美元（如 880019 = 8800亿）
                    c.execute(
                        """INSERT OR REPLACE INTO observations 
                        (series_id, timestamp, value, source, retrieved_at) 
                        VALUES (?, ?, ?, ?, datetime('now'))""",
                        ('TGA_DAILY', rec['record_date'], 
                         float(rec['open_today_bal']),
                         'treasury_fiscal_data')
                    )
                    count += 1
                except Exception:
                    pass
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        print(f"  财政部API失败: {str(e)[:80]}")
        return 0

# ============ C. 纽约联储 RRP（官方权威源） ============
def fetch_nyfed_rrp():
    """纽约联储官方 RRP（权威源）"""
    url = "https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json"
    try:
        r = requests.get(url, params={'startDate': '2024-01-01'}, timeout=30, proxies=PROXIES)
        if r.status_code != 200:
            return 0
        data = r.json()
        ops = data.get('repo', {}).get('operations', [])
        if not ops:
            return 0
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        count = 0
        for op in ops:
            try:
                # totalAmtAccepted 单位：美元 → 十亿美元
                amt_usd = float(op.get('totalAmtAccepted', 0))
                amt_billion = amt_usd / 1_000_000_000
                c.execute(
                    """INSERT OR REPLACE INTO observations 
                    (series_id, timestamp, value, source, retrieved_at) 
                    VALUES (?, ?, ?, ?, datetime('now'))""",
                    ('RRP_NYFED', op['operationDate'], amt_billion, 'nyfed_official')
                )
                count += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        print(f"  纽约联储API失败: {str(e)[:80]}")
        return 0

if __name__ == "__main__":
    print("=" * 60)
    print("  增强数据采集")
    print("=" * 60)
    
    print("\n[1/3] FRED 补充序列...")
    for fred_id, local_id in FRED_SERIES.items():
        n = fetch_fred_csv(fred_id, local_id)
        print(f"  ✅ {fred_id:15s} -> {local_id:20s} {n} 条")
        time.sleep(0.3)
    
    print("\n[2/3] 财政部每日TGA...")
    n = fetch_treasury_daily_tga()
    print(f"  ✅ TGA_DAILY: {n} 条")
    
    print("\n[3/3] 纽约联储官方RRP...")
    n = fetch_nyfed_rrp()
    print(f"  ✅ RRP_NYFED: {n} 条")
    
    print("\n🎉 增强数据采集完成！")