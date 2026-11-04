# -*- coding: utf-8 -*-
"""collectors/realtime_market.py - 终极多源瀑布流实时行情"""
import sqlite3
import requests
import re
import os
from datetime import datetime, timezone

DB_PATH = 'data/macro.db'
FRED_API_KEY = os.environ.get('FRED_API_KEY', '')

# ================= 1. Yahoo 原生 =================
def fetch_yahoo_raw(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                timestamps = result[0].get('timestamp', [])
                closes = result[0].get('indicators', {}).get('quote', [{}])[0].get('close', [])
                for ts, c in zip(reversed(timestamps), reversed(closes)):
                    if c is not None:
                        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d')
                        return d, float(c)
    except Exception:
        pass
    return None, None

# ================= 2. 腾讯财经 =================
def fetch_tencent(code):
    url = f"https://qt.gtimg.cn/q={code}"
    headers = {"Referer": "https://finance.qq.com/"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            match = re.search(r'~([\d.]+)~', r.text.encode('latin1').decode('gbk'))
            if match:
                return datetime.now().strftime('%Y-%m-%d'), float(match.group(1))
    except Exception:
        pass
    return None, None

# ================= 3. 新浪财经 =================
def fetch_sina(symbol):
    """新浪美股代码格式: gb_$inx (标普500), gb_$vix (VIX)"""
    url = f"https://hq.sinajs.cn/list={symbol}"
    headers = {"Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.text.encode('latin1').decode('gbk').split('="')
            if len(data) > 1:
                fields = data[1].split(',')
                # 新浪美股接口: fields[1] 是当前价, fields[3] 是时间(可能无)
                return datetime.now().strftime('%Y-%m-%d'), float(fields[1])
    except Exception:
        pass
    return None, None

# ================= 4. 东方财富 =================
def fetch_eastmoney(secid):
    """东财美股代码格式: 105.SPX (标普500), 100.NDX"""
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43"
    try:
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            val = r.json().get('data', {}).get('f43')
            if val:
                return datetime.now().strftime('%Y-%m-%d'), float(val) / 100.0
    except Exception:
        pass
    return None, None

# ================= 5. AkShare =================
def fetch_akshare(symbol_name):
    try:
        import akshare as ak
        # 简单抓取新浪的实时行情作为聚合库兜底
        if symbol_name == 'SP500':
            df = ak.index_us_stock_sina(symbol=".INX")
            return df.iloc[-1]['date'], float(df.iloc[-1]['close'])
        elif symbol_name == 'VIX':
            df = ak.index_us_stock_sina(symbol=".VIX")
            return df.iloc[-1]['date'], float(df.iloc[-1]['close'])
    except Exception:
        pass
    return None, None

# ================= 6. FRED (终极保底) =================
def fetch_fred(series_id):
    if not FRED_API_KEY: return None, None
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {"series_id": series_id, "api_key": FRED_API_KEY, "file_type": "json", "sort_order": "desc", "limit": 1}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            obs = r.json().get('observations', [])
            for o in obs:
                if o['value'] != '.':
                    return o['date'], float(o['value'])
    except Exception:
        pass
    return None, None

# ================= 瀑布流调度器 =================
def get_realtime_data(data_type):
    """依次尝试各个数据源，只要拿到就返回"""
    print(f"  🔄 开始拉取 {data_type} 实时数据...")
    
    # 针对不同资产的备选源定义
    sources = []
    if data_type == 'SP500':
        sources = [
            ("Yahoo", lambda: fetch_yahoo_raw('^GSPC')),
            ("腾讯", lambda: fetch_tencent('usINX')),
            ("新浪", lambda: fetch_sina('gb_$inx')),
            ("东财", lambda: fetch_eastmoney('100.SPX')),
            ("AkShare", lambda: fetch_akshare('SP500')),
            ("FRED", lambda: fetch_fred('SP500'))
        ]
    elif data_type == 'VIX':
        sources = [
            ("Yahoo", lambda: fetch_yahoo_raw('^VIX')),
            ("腾讯", lambda: fetch_tencent('usVIX')),
            ("新浪", lambda: fetch_sina('gb_$vix')),
            ("东财", lambda: fetch_eastmoney('100.VIX')),
            ("AkShare", lambda: fetch_akshare('VIX')),
            ("FRED", lambda: fetch_fred('VIXCLS'))
        ]

    # 遍历瀑布流
    for source_name, func in sources:
        date, val = func()
        if val is not None:
            print(f"    ✅ [{source_name} 成功] {data_type}: {val:.2f} ({date})")
            return date, val, source_name
        else:
            print(f"    ⚠️ [{source_name} 失败] 尝试降级下一个源...")
            
    print(f"  ❌ {data_type} 所有数据源均失败，将保留本地历史值")
    return None, None, None

def update_db():
    spx_date, spx_val, spx_src = get_realtime_data('SP500')
    vix_date, vix_val, vix_src = get_realtime_data('VIX')

    if spx_val is not None and vix_val is not None:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))",
                     ('SP500', spx_date, spx_val, f'rt_{spx_src}'))
        conn.execute("INSERT OR REPLACE INTO observations (series_id, timestamp, value, source, retrieved_at) VALUES (?, ?, ?, ?, datetime('now'))",
                     ('VIX', vix_date, vix_val, f'rt_{vix_src}'))
        conn.commit()
        conn.close()
        print(f"  🎯 已强制覆写数据库!")
    else:
        print("  ⚠️ 未获取到完整数据，跳过数据库更新")

if __name__ == "__main__":
    update_db()